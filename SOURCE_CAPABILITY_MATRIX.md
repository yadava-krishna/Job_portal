# Source capability matrix and compliance register

Last reviewed: 2026-11-05. "Verified" means checked live from this server on that date; everything else is stated as
documented by the provider or as unknown. JobPilot only uses a source when access is documented and authorised. When
it is not, the integration stays disabled and the user is given a manual path instead. There are no workarounds.

## 1. Job discovery sources

| Source | Discovery API | Auth | Application API | Employer permission | Rate limits | Coverage | Work mode | Terms / restrictions | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Greenhouse** Job Board API | Yes, documented (`boards-api.greenhouse.io/v1/boards/{board}/jobs`) | None (public read) | Yes (`POST …/jobs/{id}`), but **needs the employer's Job Board API key** | Employer publishes the board; submission needs the employer's key | Not published; JobPilot caches each board 30 min, 404s 6 h | Global (per employer) | Not provided; inferred from text, labelled | Read-only public data; cite the employer's own job page | **Live** (Phase 2) |
| **Lever** Postings API | Yes, documented (`api.lever.co/v0/postings/{site}`) | None | Yes (`POST …/apply`), but **needs the employer's API key** | As above | Not published; cached | Global (+ EU endpoint) | `workplaceType` | Read-only | **Live** |
| **Ashby** Posting API | Yes, documented (`api.ashbyhq.com/posting-api/job-board/{board}`) | None | Application API exists for **employer API keys only** | As above | Not published; cached | Global | `isRemote` / `workplaceType` | Read-only | **Live** |
| **SmartRecruiters** Posting API | Yes, documented (`api.smartrecruiters.com/v1/companies/{id}/postings`). Verified: Bosch has 5,000 postings, 105 in India in the first 1,000 read | None | Application API needs **partner/employer credentials** | As above | Not published; JobPilot reads ≤ 1,000 postings per board (10 pages) and fetches a job ad only for postings a search keeps (cached 6 h) | Global | `remote` / `hybrid` flags | Read-only; unknown company names return an empty list (not an error), so JobPilot shows "0 open roles" rather than claiming the board was verified | **New (Stage F)** |
| **Recruitee** Careers Site API | Yes, documented (`{company}.recruitee.com/api/offers/`). Verified (bunq: 24 offers) | None | No public candidate API for third parties | Employer publishes the careers site | Not published; cached | Global (mostly EU) | `remote` / `hybrid` / `on_site` | Read-only | **New (Stage F)** |
| **Workable** | The public "jobs widget" endpoint answers (`apply.workable.com/api/v1/widget/accounts/{sub}`), but it is **not in Workable's documented API**. The documented API needs an employer token | Employer token for the documented API | Employer only | Yes | Unknown | Global | `telecommuting` | Undocumented for third parties | **Not enabled: needs your decision** |
| **Personio** XML feed | Documented per company (`{company}.jobs.personio.de/xml`) | None | No | Employer publishes | Unknown | Mostly DACH | Partial | Read-only | Not implemented (low India coverage) |
| **Workday, SuccessFactors, iCIMS, Taleo** | No public documented job API for third parties (Workday's careers JSON is internal) | n/a | No | n/a | n/a | n/a | n/a | Undocumented/private endpoints are **not used** | **Not supported**: users apply on the employer site |
| **Adzuna** | Yes, documented (`api.adzuna.com/v1/api/jobs/{country}/search`) | **App ID and key (free registration)** | No | No | Documented free-tier quota (see your Adzuna dashboard) | India (`in`) and 15+ countries | Partial | Attribution to Adzuna; links to Adzuna's redirect page | **Built, waiting for your keys** |
| **Jooble** | REST API on request | **API key from Jooble** | No | No | Per agreement | Global incl. India | Partial | Partner agreement | Not implemented (needs your key) |
| **Careerjet** | Public API | **Affiliate ID** | No | No | Per agreement | Global incl. India | No | Affiliate terms; must show Careerjet links | Not implemented (needs your affiliate ID) |
| **Remotive** | Public API (`remotive.com/api/remote-jobs`). Verified 200 | None | No | No | 30 req/min token bucket | Remote jobs | Remote only | Attribution and link-back embedded | **Live (2026-11-06)** |
| **Himalayas** | Public API (`himalayas.app/jobs/api`). Verified 200 | None | No | No | 30 req/min token bucket | Remote jobs | Remote | Attribution and link-back embedded | **Live (2026-11-06)** |
| **RemoteOK** | Public API (`remoteok.com/api`). Verified 200 | None | No | No | 20 req/min token bucket | Remote jobs | Remote | Attribution and link-back embedded | **Live (2026-11-06)** |
| **Arbeitnow** | Public API (`arbeitnow.com/api/job-board-api`). Verified 200 | None | No | No | 30 req/min token bucket | Global / Europe | Remote & on-site | Attribution and link-back embedded | **Live (2026-11-06)** |
| **National Career Service (India, ncs.gov.in)** | Public portal parsing & structured notices | None | No | Public sector portal | 15 req/min, respect robots.txt | India (all states) | On-site / hybrid | Public sector citizen access | **Live (2026-11-06)** |
| **Indian Government (UPSC, SSC, ISRO, DRDO)** | Public recruitment notices & RSS feeds | None | No | Public sector notifications | 15 req/min | India national | On-site | Official public employment notices | **Live (2026-11-06)** |
| **Indian Academic Institutes (IIT Bombay, Delhi, Madras, IISc)** | Public faculty & staff recruitment portals | None | No | Academic hiring notices | 15 req/min | India national | Academic / Research | Official university postings | **Live (2026-11-06)** |
| **Schema.org JSON-LD / RSS / Sitemaps** | Structured metadata extraction (`scrapling.parser.Adaptor`) | None | No | Employer published microdata | Domain-scoped token bucket | Global | From schema | Read-only Schema.org standard | **Live (2026-11-06)** |
| **Company careers page (user-submitted URL)** | SSRF-vetted explorer (`CareerUrlConnector`). Checks ATS embeds, JSON-LD, RSS, sitemaps | None | No | Uses employer's published site | 20 checks/hour per user; SSRF protected | Any | From detected board | HTTPS only, public IPs only, DNS vetted; no circumvention | **Live (2026-11-06)** |
| **Job-alert e-mails** (LinkedIn, Indeed, Naukri alerts in the user's own mailbox) | IMAP, read-only, user's own app password (stored encrypted) | User's own mailbox | No | No | Checked on schedule | Wherever the user gets alerts | From the e-mail, if stated | Only the user's own mail; posting dates marked *estimated* | **Live** (Phase 1) |
| **Clip / import** (bookmarklet, URL, file) | User action on a page they are viewing | None | No | No | n/a | Any site | From the page | User-initiated; no automation | **Live** |

## 2. LinkedIn, Indeed, Naukri

| Platform | Official job-search API for third parties | Official apply API | Status in JobPilot |
|---|---|---|---|
| LinkedIn | None. Job Posting and Apply Connect APIs are for approved ATS partners posting employers' jobs, not for job-seeker apps | Apply Connect only for approved ATS partners | Disabled. Use alert e-mails, clip or import; open the original page; confirm in JobPilot |
| Indeed | None. The Publisher Jobs API was retired; Job Sync is for employers/ATS | Indeed Apply is for employers/ATS partners | Disabled. Same manual path |
| Naukri | None public (Naukri RMS is recruiter-side) | None | Disabled. Same manual path |

JobPilot never scrapes these sites, uses hidden APIs, reads their cookies, asks for their passwords, proxies their
logins, or automates anything on them. Users sign in to those platforms themselves, in their own browser.

## 3. Direct application (Method 1)

Greenhouse, Lever, Ashby and SmartRecruiters document **employer-side** application APIs. Each needs an API key
issued to the employer (or an approved integration partner). JobPilot has no such keys and is not permitted to use an
employer's keys on candidates' behalf, so **direct application is disabled for every source**. The API reports this
as `direct_apply: false`. If an employer or provider grants JobPilot authorised access in future, direct submission
would be enabled for that employer only after testing in their sandbox, with explicit user review, and recording the
provider's confirmation reference.

## 4. Compliance register

| Area | Rule | How it is enforced |
|---|---|---|
| Official APIs only | Only documented public endpoints; undocumented ones (Workable widget, Workday JSON) stay off | Fetchers exist only for documented APIs; reviewed in this file |
| Request volume | Boards are cached (30 min; 6 h for 404s). SmartRecruiters: ≤ 10 list pages per board and detail only for kept postings. Per-user limits on careers-page checks | `ats/cache.py`, `ats/smartrecruiters.py`, `company_service._from_careers_page` |
| Failure isolation | One failing board or source never stops the others; each source's outcome is shown | `source_results` per run, Sources tab |
| robots / bot protection | Careers-page checks read one public page like a browser would. Bot-protected pages are reported as unreachable, with no retries or evasion | `careers_page.py` |
| Personal data | Profile data is sent only to the employer's form the user is filling, on click. Nothing goes to third parties; no analytics | Extension SECURITY.md |
| Credentials | No third-party platform credentials are stored, except the user's own IMAP app password (encrypted) for their own alert e-mails | `CredentialCipher` |
| Applications | Never submitted automatically; *Applied* only on the user's explicit confirmation | `application_service`, extension `safeClick`, tests |

---

### Additions from this Session (2026-11-06)
- **Scrapling Engine Integration**: Integrated Scrapling 0.5.1 (`scrapling[fetchers]==0.5.1`) with async semaphore concurrency, DNS-level SSRF rejection, and robots.txt parsing cache via urllib/protego.
- **Source Policy Registry (`source_policies.py`)**: 50+ pre-registered sources with strict permission models (`PUBLIC_API`, `PERMITTED_SCRAPE`, `ASSISTED_ONLY`).
- **Expanded Connector Catalogue**: Activated Remotive, Himalayas, RemoteOK, Arbeitnow, NCS India, Government (UPSC, SSC, ISRO, DRDO), Academic (IITs, IISc), and Schema.org JSON-LD / RSS / Sitemap crawlers.
- **Zero-Scrape Invariant Maintained**: LinkedIn, Indeed, and Naukri continue to be strictly classified as `ASSISTED_ONLY` with zero automated scraping or credential interception.

