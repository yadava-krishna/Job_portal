# JobPilot discovery engine: top-level plan

> **Superseded on 2026-11-17** by the owner's reviewed blueprint, `JOBPILOT_JPSE_BLUEPRINT.md`. That document is the plan of record. This draft stays only as background: the measurements in section 1 are its evidence.

Owner document. Written 2026-11-17. Nothing in this plan is built yet.

## 1. What a discovery run spends its time on (measured 2026-11-17)

Run 73, a manual run by user 3, took about 7.5 minutes:
- It checked 206 company boards (26,137 listings) and found 62 matches, none of them new.
- The four job feeds (Himalayas, RemoteOK, Remotive, Arbeitnow) took about **10 s**.
- The company boards took about **6 min 20 s**.

Board benchmark, inside the backend container, 6 boards per ATS:

| ATS | Boards in catalogue | Time per board | Network share | Python parse share |
|---|---|---|---|---|
| Greenhouse | 126 | 0.40 s | 86% | 14% |
| Lever | 50 | 2.98 s | 99% | 1% |
| Ashby | 25 | 0.33 s | 99.5% | 0.5% |
| SmartRecruiters | 5 | 1.55 s | 99.7% | 0.3% |

Where the time goes (`backend/services/saved_search_service.py::_board_items`):
1. **Boards are fetched one at a time.** Each fetch opens a new HTTP connection (`ats/base.py::_get_json_once` creates a new `httpx.Client` per request), so every board pays DNS, TCP and TLS setup again.
2. Every board then does its own database work: health recording, closed-job detection, and a progress commit.
3. Every run re-downloads every board in full, even when nothing on it changed. Run 73 found 0 new jobs, so all 7.5 minutes were spent confirming nothing had changed.
4. The run happens when the user clicks **Discover**, so the user waits for the whole crawl.

**Conclusion:** CPU is not the bottleneck, so rewriting the same sequential loop in C would save under 10%. The large gains come from:
- fetching boards in parallel;
- skipping unchanged boards;
- most of all, crawling in the background so that clicking Discover is just a database query.

These gains are independent of the programming language. The plan below does them first. A native (C) engine comes after that, as Stage 3, for the point where the catalogue grows to tens of thousands of boards or to HTML career sites, where parsing cost does start to matter.

## 2. Target architecture: separate crawling from searching

```
                ┌──────────────────────── CRAWLER (always running, no user waiting) ──────────────────────┐
 crawl_targets ─►  Scheduler ─► Fetcher pool ─► Change filter ─► Parser ─► Writer ──► postings (Postgres)  │
 (boards, feeds)   (frontier)   (async, polite)  (ETag / hash)   (per ATS)  (batched)        │             │
                └──────────────────────────────────────────────────────────────────────────┼─────────────┘
                                                                                            │ "changed ids"
                ┌──────────────────────── MATCHER (Python, existing code) ─────────────────▼─────────────┐
                │ normalise (core/locations, core/salary) ─► candidate users (inverted index) ─► score  │
                │ ─► user_jobs + notifications                                                          │
                └───────────────────────────────────────────────────────────────────────────────────────┘
 User clicks Discover ─► query the index with their filters + scores already computed ─► answer in < 2 s
```

- **Crawler.** Its only job is keeping `jobs` an accurate mirror of every board and feed. It runs on its own schedule and knows nothing about users.
- **Matcher.** It reacts only to postings that changed, and scores them only for users whose searches could match them.
- **Discover button.** It no longer starts a crawl. It runs a filtered query over the index, and optionally asks the crawler to refresh the user's watched companies first, with the results streaming in.

## 3. The algorithm

### 3.1 Scheduler (the frontier)
- A **min-heap keyed by `next_due_at`**, with one entry per crawl target (a board, or a feed page).
- `next_due_at = last_fetched_at + interval`, where the **interval adapts**:
  - when the board changed: `interval = max(MIN, interval / 2)`, so active boards are visited more often;
  - when it was unchanged: `interval = min(MAX, interval × 1.5)`, so quiet boards are visited less;
  - start values: MIN = 15 min, MAX = 12 h, initial = 1 h;
  - a user watching the company, or an open saved search, caps the interval at 1 h.
- Each target also carries a `priority`: user-requested refreshes go first, then targets that are overdue the longest.
- The state lives in Postgres (`crawl_state`: target, etag, last_modified, body_hash, interval, next_due_at, failures, last_status). A restart therefore resumes exactly where it stopped, the same way the catch-up logic works today.

### 3.2 Politeness and safety. These rules are not optional
- **Per-host token bucket.** Rate and burst come from `source_policies`, the existing table of per-site rules.
- **Per-host in-flight cap**: start at 2 concurrent requests per API host, and raise it only while no 429 responses come back.
- **Global in-flight cap**: about 32.
- **robots.txt:** fetched once a day per host and cached, through the same rules as the current shared client.
- **429 or 5xx:** exponential backoff with jitter, honouring `Retry-After`.
- **Per-host circuit breaker:** after 5 consecutive failures, pause the host for 30 minutes.
- **SSRF guard:** resolve the hostname, refuse private, loopback or link-local addresses, and re-check after every redirect.
- **Caps:** response bytes (8 MB), redirects (5), connect and read timeouts.
- **Never crawled:** LinkedIn, Naukri, Indeed, Glassdoor. The deny-list is enforced in the fetcher, not left to the caller.
- **User agent:** an honest, identifiable one, as today.

### 3.3 Fetcher
- **Persistent connection pools per host**, using HTTP/2 where offered. The roughly 300 Greenhouse requests then share a single TLS connection.
- **Conditional requests:** send `If-None-Match` / `If-Modified-Since` with the stored ETag and date. A `304 Not Modified` costs a few hundred bytes and needs no parsing.
- Compression enabled (gzip and brotli).

### 3.4 Change filter. This is the biggest saving on repeat runs
1. Board level: when the server returns 304, or when the body's fast hash (xxHash3 or BLAKE3) equals `body_hash`, stop. Nothing changed.
2. Posting level: when the body did change, parse it and hash each posting's meaningful fields (title, location, pay, description, URL). Only postings with a **new or different hash** move downstream.
3. Closed detection: compute the set difference between the posting keys stored for this board and the keys now live. The ones that disappeared get `closed_at`. This is the same rule as today's `_close_missing`, applied once per board change instead of once per user run.

### 3.5 Parser
- One extractor per source format, mapping each raw posting to the fields in `NormalizedJob`. The source formats are:
  - Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee JSON;
  - the four feeds;
  - JSON-LD `JobPosting` for HTML career pages.
- Work in streaming mode where possible, with bounded memory.
- **Keep normalisation in exactly one place (Python).** The crawler stores raw location and salary text. `core/locations.py` and `core/salary.py` run on changed rows only. Writing these rules a second time in C would make the two copies drift apart.

### 3.6 Writer
- Batch every 500 postings or 2 seconds:
  1. `COPY` into an unlogged staging table;
  2. a single `INSERT … ON CONFLICT (dedup_key) DO UPDATE … WHERE hash changed`;
  3. a single transaction per batch.
- After each batch, insert one `task_queue` row (or send `NOTIFY postings_changed`) carrying the changed job ids.

### 3.7 Deduplication
- Exact matches: `dedup_key` (normalised company, title and location) is the existing rule.
- Near-duplicates: a 64-bit **SimHash** of the description. Two postings at the same company with a Hamming distance of 3 or less are one job. This catches re-posts with small edits.

### 3.8 Matching (the existing Python code, called differently)
- Build an **inverted index of user searches**, keyed on normalised title tokens, country and remote scope, and refresh it when a search changes.
- For each changed posting, look up the users whose searches could match, then run `scoring_v2` for those users only. Today the work is (every board × every search); it becomes (changed postings × interested users).

## 4. Expected results (estimates from the measurements above, to be confirmed by benchmark)

| | Today | Stage 1: Python, parallel and incremental | Stage 2: crawler and search separated | Stage 3: native engine |
|---|---|---|---|---|
| Full crawl of 206 boards | about 6.5 min | **about 45–60 s** (Lever is the slowest host) | same, in the background | about 40–55 s (still waiting on the network) |
| Repeat crawl when nothing changed | about 6.5 min | **about 15–25 s** (304s and hash skips) | same, in the background | about the same |
| User waits after clicking Discover | about 7.5 min | about 1 min | **under 2 s** | under 2 s |
| Comfortable catalogue size | about 200 boards | about 2,000 | about 10,000 | 100,000+ boards, HTML sites |

Stage 3 adds speed only through parsing and memory efficiency at large scale. At today's 206 boards it adds almost nothing.

## 5. Stages and exit criteria

**Stage 1: fast fetch, inside the current Python service (about 2–3 days).**
- Replace the sequential `_board_items` loop with `asyncio` + `httpx.AsyncClient`:
  - one pooled client per host;
  - the per-host token bucket and in-flight caps from §3.2.
- Store ETag, Last-Modified and body hash per board, and skip unchanged boards.
- Batch the per-board database writes, and commit progress every N boards instead of after every board.
- *Exit:* the same results as today on a recorded fixture set; a full run under 90 s; an unchanged run under 30 s; no 429 responses in a week of logs.

**Stage 2: separate crawling from searching (about 1 week).**
- Add the `crawl_targets` and `crawl_state` tables (additive migration).
- Run the crawler as its own container service, with `restart: unless-stopped` and CPU and memory caps.
- Add matching from change events, and the inverted index of searches.
- Discover becomes a query over the index. "Refresh my companies now" pushes high-priority targets to the front of the queue.
- *Exit:* Discover answers in under 2 s; a new posting on a watched board reaches the feed within one crawl interval; the existing discovery tests still pass.

**Stage 3: native engine (C). Detailed design in Part B below.**
- Triggers to start it:
  - over 10,000 boards;
  - HTML career-site crawling at volume;
  - or a crawler-host CPU above 50% sustained.
- Proposed C stack:
  - `libcurl` multi interface, for event-driven HTTP/2 with connection reuse;
  - `c-ares`, for asynchronous DNS;
  - `yyjson` or `simdjson`, for JSON;
  - `lexbor`, for HTML and JSON-LD;
  - `xxhash`;
  - `libpq`, using COPY.
- It replaces the crawler process from Stage 2 only, using the same tables. The Python matcher stays unchanged.
- **Safety requirements for C, which parses untrusted internet content:**
  - libFuzzer fuzzing for every parser;
  - ASan and UBSan builds in CI;
  - running as a non-root, seccomp-restricted container with read-only root and outbound network only;
  - a database role that may write only `crawl_state` and the staging tables.
- *Recommendation:* consider **Rust (`reqwest`/`hyper` + `serde_json` + `tokio`) or Go** instead of C. Speed is about the same, and memory-safety bugs from parsing internet content can't happen. The design above is the same whichever language is chosen.

## 6. Decisions for the owner
1. Approve Stage 1, which gives most of the speed-up with the lowest risk.
2. Choose the crawl interval limits and how often watched companies are refreshed. These are the §3.1 defaults.
3. Choose the language for Stage 3, if and when it's needed: C as requested, or Rust or Go as recommended.
4. Choose how much host capacity the crawler service may use (CPU and memory caps).

---

# Part B: C engine detailed design (draft for owner review)

The owner asked for a C engine that builds its own hash maps dynamically and gives the fastest possible search. Part B replaces the short Stage 3 description above. Stages 1 and 2 still come first, because they remove the network wait, which no language can do. Part B is the engine that sits behind Stage 2's "crawler" and "Discover" boxes.

Working name: **`jpse`** (JobPilot search engine). It is a single C17 process in its own container. Postgres stays the source of truth: the engine can always be rebuilt from Postgres, so losing or replacing the engine never loses data.

## B1. What the engine does

| Part | Job | Replaces |
|---|---|---|
| **Crawler** | Fetches every board and feed politely, keeps only what changed, and writes it to Postgres | Stage 1 and 2 Python crawler |
| **Index** | Holds **every listing ever crawled**, not only the ones that matched someone: about 26,000 today, designed for 1–5 million | Today only matched jobs are stored (343 rows), so every search has to crawl again |
| **Search** | Answers "jobs for this search, these filters, top 50" in **under 5 ms** (p99, 1 million postings) | `jobs` SQL queries + the crawl inside the Discover button |

Python keeps normalisation (`core/locations.py`, `core/salary.py`), the full match scoring (`scoring_v2`), notifications and the API. The engine finds candidates fast. Python scores the top few hundred precisely.

## B2. Hash maps: choosing the best structure at build time

No single hash map is the fastest for every use. The engine picks a structure for each table from what it knows about that table: its size, whether it changes, how often it is read, and the key type. It re-decides whenever a table is rebuilt: at segment build, at merge, and when the skills taxonomy reloads.

### B2.1 The structures available
1. **Swiss table** (open addressing, groups of 16 one-byte control tags, probed with SIMD (SSE2 / NEON)). Used for large tables that change.
   - Maximum load 7/8.
   - One cache line per lookup in the common case.
   - Tombstone-free deletes inside a group.
2. **Minimal perfect hash (PTHash or BBHash family) + fingerprint array.** Used for large tables that **never change after build**.
   - About 2–3 bits per key, no empty slots, and exactly one probe.
   - An 8–16-bit fingerprint per slot rejects keys that aren't present.
3. **Sorted small array with SIMD compare.** Used for tables of up to about 16 keys, where a linear scan beats hashing.
4. **Sharded Swiss table.** Used for tables written from many threads.
   - `2 × cores` shards, rounded up to a power of two, chosen by the hash's top bits.
   - Each shard has its own spin-then-sleep lock, so writers on different shards never block each other.
5. **Cuckoo filter.** Used in front of very large "have we seen this?" sets: about 12 bits per entry, supports deletion, and skips the exact-table lookup on a definite "no".

### B2.2 Decision rule, per table
```
if table is immutable (built once per segment / taxonomy load):
    n ≤ 16        → sorted array (SIMD scan)
    else          → minimal perfect hash + fingerprints
else (mutable):
    written by >1 thread → sharded Swiss table
    n_expected ≥ 50M or mostly negative lookups → cuckoo filter + Swiss table
    else          → Swiss table
```
- `n_expected` comes from a **HyperLogLog** counter that each table keeps, using 12 KB.
- Tables are pre-sized from it, so a table that is about to grow never rehashes repeatedly.

### B2.3 Growing without pauses
- Mutable tables use **incremental resize**: while a resize is under way, both the old and new arrays exist, each insert or lookup moves 64 slots across, and lookups check both.
- No single request ever pays for a full rehash, which keeps p99 latency flat.
- A table shrinks when its load falls below 1/4 for 10 minutes.

### B2.4 Hash functions
- Short keys (terms, hosts, posting keys): **rapidhash / wyhash-class**, seeded per process. The random seed resists hash-flooding attacks from crafted input.
- Response bodies and posting content: **XXH3-64** (change detection, §3.4).
- Near-duplicate detection: **64-bit SimHash** of description shingles.

### B2.5 The tables the engine holds

| Table | Key → value | Structure chosen |
|---|---|---|
| Term dictionary (sealed segment) | term string → term id + posting-list offset | perfect hash |
| Term dictionary (live segment) | term → term id | Swiss table |
| String interning (companies, locations, titles) | string → u32 id | sharded Swiss table, strings stored in an arena |
| Skills / synonyms (O2C → order to cash) | alias → canonical skill id | perfect hash, rebuilt when the taxonomy changes |
| Countries, regions, ATS names, modes | name → small id | sorted array or perfect hash (static) |
| Posting key → doc id | `ats:board:id` hash → u32 | Swiss table |
| Content hash per doc | doc id → XXH3 | flat array indexed by doc id (no hashing needed) |
| Crawl host state (politeness) | host → token bucket, in-flight count, breaker | sharded Swiss table |
| Board state | board id → ETag, last-modified, body hash, interval | Swiss table, persisted to `crawl_state` |
| Seen URLs (HTML crawling, large) | URL hash → seen | cuckoo filter + Swiss table |
| Near-duplicate bands | each of four 16-bit SimHash bands → doc ids | 4 Swiss tables. By the pigeonhole principle, any two docs within Hamming distance 3 share at least one exact band, so a lookup finds them all. |

## B3. The search index

### B3.1 Segments: lock-free reads while writing
- The index is a list of **segments**:
  - one small mutable **live segment**, where new and changed postings go;
  - many **sealed segments**, which are immutable and memory-mapped files.
- The live segment seals every 10,000 docs or every 60 s. A background thread **merges** small segments into larger ones, as in an LSM tree or Lucene.
- Deletes and updates set a bit in the owning segment's **tombstone bitmap**. An updated posting is re-added to the live segment.
- Readers take a **snapshot**, a reference-counted list of segments, swapped atomically with RCU-style epochs. Searches never wait on writes, and writes never wait on searches.

### B3.2 What is indexed for each posting
- **Text fields** (tokenised: lower-cased, ASCII-folded, stemmed only for the description):
  - title (weight 3.0);
  - skills (weight 2.5, already canonicalised through the synonym table);
  - company (weight 1.5);
  - description (weight 1.0).
- **Filter fields**, each value held as a bitmap:
  - country;
  - remote scope (countries or regions);
  - work mode, employment type, seniority, ATS/source;
  - freshness state;
  - sponsorship.
- **Numeric columns**, stored as flat arrays by doc id:
  - posted date and first seen;
  - annual salary minimum and maximum, plus currency id (never converted, the same rule as Phase 3);
  - experience years.

### B3.3 Posting lists
- **Filter fields:** **Roaring bitmaps**. Each 65,536-id block automatically picks an array, a bitmap or run-length encoding, whichever is smallest for its density. AND, OR and NOT run with SIMD over 64-bit words.
- **Text terms:** blocks of 128 doc ids, delta-encoded and **bit-packed** (StreamVByte or SIMD-BP128) with term frequencies. Each block keeps a **max-score** value for early termination (B3.4).
- **Numeric ranges** (salary at least X, posted in the last N days): a range-encoded bitmap per bucket for coarse cut-offs, then an exact check against the flat column for the remaining docs.

### B3.4 Query algorithm (one search)
```
1. Parse the saved search → required filters, text terms, ranking weights.
2. Expand terms through the synonym perfect hash (O2C → "order to cash", "o2c").
3. FILTER = AND of filter bitmaps (country ∪ remote-open-to-country, mode, freshness≠closed/expired, …)
           AND NOT tombstones; cheapest (smallest) bitmap first.
4. If no text terms: rank FILTER by posted date/first seen → top k by a k-sized heap. Done.
5. Else run Block-Max WAND over the term posting lists, visiting only docs in FILTER:
     score = BM25F(title, skills, company, description)
           + freshness boost (decays with age)
           − duplicate penalty (SimHash group already seen in results)
   Block-Max WAND skips whole blocks whose maximum possible score can't enter the current top k.
6. Group by dedup group (one card per company + title, as in Phase 3).
7. Return the top k (default 200) doc ids + coarse scores → Python re-scores with scoring_v2 and returns 50.
```
Per-query cost grows with the size of the filtered set and the lists it touches, not with the total catalogue size.

### B3.5 Other search features
- **Prefix and typo search** (for the search box): an **FST** (finite-state transducer) over each sealed segment's term dictionary, with Levenshtein-automaton matching at edit distance 1 for terms of 5 characters or more.
- **"Why it matched"**: the engine returns which terms and filters hit. The existing match breakdown stays in Python.
- **Saved-search alerts**: run in reverse (percolation). Each saved search is compiled once into a small query. When a posting changes, the engine looks up the saved searches indexed by its title and skill terms in a Swiss table, then checks only those. This is §3.8's inverted index of searches, done in C.

## B4. Threads and memory
- Thread pools:
  - **1 I/O thread**: libcurl multi interface + c-ares, event loop, all HTTP;
  - **N parse threads**: N = cores − 2, capped at 8;
  - **1 index writer**: the only thread that changes the live segment;
  - **1 merger**;
  - **M query threads**, each serving requests from a Unix socket.
- Lock-free single-producer/single-consumer ring buffers between the stages.
- **Memory:**
  - an arena per segment, freed whole when the segment is merged away;
  - no per-posting `malloc`;
  - descriptions are **not** kept in memory. Only their tokens are indexed; the text stays in Postgres.
- **Budget:** about 1.5 KB per posting in RAM, so 1 million postings is about 1.5 GB and today's 26,000 is under 50 MB. The container gets a hard memory cap (say 1 GB now). Past the cap, the engine falls back to memory-mapped segments that the operating system pages in and out.
- **Persistence:** sealed segments are files in a Docker volume. After a crash, the engine reloads the segments and replays changes since the last seal from Postgres (`updated_at > seal_time`). After a version upgrade, it rebuilds fully from Postgres (26,000 docs in about 1 s).

## B5. How Python talks to it (nothing breaks)
- The API runs over a **Unix domain socket**, with length-prefixed binary frames (or MessagePack). The commands are:
  - `search(query, filters, k)`;
  - `suggest(prefix)`;
  - `refresh(board_ids, priority)`;
  - `stats()`;
  - `health()`.
- The backend calls the engine behind a **feature flag**. If the engine is down, slow (over 200 ms) or flagged off, the backend falls back to today's Postgres query path. The UI never breaks.
- **Shadow mode first:** for 1–2 weeks, run both paths and log any difference in the top 50 before switching.

## B6. Safety: C reads untrusted internet data
These are required before the engine handles live traffic:
- **Fuzzing:** every parser (JSON per ATS, JSON-LD, HTML, HTTP headers, the socket protocol) runs under libFuzzer + AFL++ in CI, plus a nightly long run.
- **Sanitisers:** ASan, UBSan and MSan builds run the whole test suite. Compiled with `-D_FORTIFY_SOURCE=3 -fstack-protector-strong -fstack-clash-protection -fPIE -Wl,-z,relro,-z,now`.
- **Only bounded operations:** a size check on every copy and length-checked string views everywhere; no `strcpy`, `sprintf` or `strcat`.
- **Container:**
  - non-root user, read-only root filesystem, seccomp profile, no added capabilities;
  - outbound HTTPS only, plus its own volume;
  - a Postgres role that may write `crawl_state`, staging tables and `jobs` upserts only.
- **Unchanged policy:** robots.txt, per-host limits, the LinkedIn/Naukri/Indeed/Glassdoor deny-list, the SSRF guard and the honest user agent. All are enforced inside the engine.

## B7. Build and test plan
| Step | Content | Exit criteria |
|---|---|---|
| B-0 | Repository layout (`engine/`), CMake, CI with sanitisers + fuzz targets, benchmark harness with recorded board fixtures | CI green; fixtures recorded |
| B-1 | Hash-map library: Swiss table, sharded Swiss table, perfect hash, cuckoo filter, incremental resize, HLL-based selection | Microbenchmarks beat `khash`/`uthash` baselines; fuzzed |
| B-2 | Crawler: libcurl multi + politeness + conditional GET + XXH3 change filter + per-ATS JSON parsers + COPY writer | Same postings as the Python crawler on the fixtures; full crawl ≤ 60 s live; 0 × 429 |
| B-3 | Index: segments, Roaring filters, bit-packed text lists, BM25F + Block-Max WAND, tombstones, merge | 1 million synthetic postings: index ≥ 50,000 docs/s; search p99 < 5 ms |
| B-4 | Socket API + Python client + feature flag + Postgres fallback | All existing backend tests pass with the flag on and with it off |
| B-5 | Shadow mode in production | Top-50 overlap ≥ 95% with today's results, or each difference explained |
| B-6 | Switch the Discover button to the engine, and percolation for alerts | Discover < 2 s end to end (< 5 ms in the engine) |

Rough effort: B-0 to B-4 take about 5–7 weeks of focused work. B-5 and B-6 add 2 weeks, mostly waiting time.

## B8. Questions for the owner's review
1. **Scope of the index:** store and index every crawled listing (recommended; this is what makes Discover instant), or only listings that matched someone (today's behaviour)?
2. **Scale target to design for:** 100,000 / 1 million / 5 million postings. This sets memory caps and the segment size.
3. **Search features in the first version:** prefix and typo search, and percolation for alerts. Both are in the plan. They can be dropped to ship sooner.
4. **Language:** C as requested, with the safety rules in B6. Rust would give the same design and speed, with memory safety enforced by the compiler.
5. **Host budget:** this machine has 12 cores and 10 GB RAM, with about 2 GB free today. The proposed cap is 1 GB RAM and 4 cores for the engine.
