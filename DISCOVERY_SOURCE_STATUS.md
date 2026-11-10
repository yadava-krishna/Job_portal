# JobPilot: Discovery Source Status

Snapshot taken 2026-11-04 against the live public APIs. Numbers change daily. The live health of every source is shown
per user under **Searches & sources → Source health**, and each run records its own per-source outcome.

## Sources

| Source | How | Status | Configuration |
|---|---|---|---|
| Greenhouse | Official Job Board API `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | **Working** | None (public). Companies come from the curated list, user watchlists or board URLs |
| Lever | Official Postings API `api.lever.co/v0/postings/{token}?mode=json` (EU: `api.eu.lever.co`) | **Working** | None (public) |
| Ashby | Official Job Postings API `api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` | **Working** | None (public). Only `isListed` postings are shown |
| Adzuna | Official Jobs API | **Prepared, disabled** | Needs `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` in `.env`. Until then every run and the health panel say "not configured". Invalid keys are reported as "Adzuna rejected the API credentials" |
| Job-alert emails (LinkedIn, Indeed, Naukri alerts) | User's own mailbox over IMAP, read-only | Working when configured | Per user: Settings → Job-alert email, and tick "Job-alert email" for a platform |
| Clipper, job links, paste, file import | User-initiated | Working | None |
| LinkedIn, Indeed, Naukri automated discovery | — | **Not provided, by design** | Their terms prohibit scraping and automation without permission. No scraping, no private APIs, no cookies. Naukri: no authorised public API was identified; to be revisited only if permission or an official integration exists |

### What each ATS provides (verified against live responses)

| Field | Greenhouse | Lever | Ashby |
|---|---|---|---|
| Full description | `content` (escaped HTML → plain text) | `descriptionPlain` + `lists` + `additionalPlain` | `descriptionPlain` (or HTML → text) |
| Posting date | `first_published` (**verified**). `updated_at` is never used as a posting date | `createdAt` (epoch ms, **verified**) | `publishedAt` (**verified**) |
| Location | `location.name` | `categories.location` / `allLocations` | `location` + `secondaryLocations` |
| Department / team | `departments[0]` | `categories.department` / `team` | `department` / `team` |
| Work mode / employment type | not provided (inferred from the description) | `workplaceType`, `commitment` | `workplaceType`, `employmentType` |
| Salary | not provided | `salaryRange` (INR converted to LPA) | compensation summary when the employer displays it |
| Job URL | `absolute_url` | `hostedUrl` | `jobUrl` |

Pagination: each of these endpoints returns the whole board in one response (no paging parameters). Responses are capped at 25 MB.

Reliability:
- 25-second timeout.
- Errors are classified: not found (cached for 6 h); transient (429, 5xx, timeouts; retried on the next run); invalid.
- One failing board never stops the others.
- Boards are shared through a 30-minute in-process cache, so many users cost one fetch per board.

## Company registry

- **Curated list** (`backend/data/ats_companies/curated_india.json`): 30 employers whose boards answered with jobs located in India (or remote-India) on 2026-11-04. Every user's starter search uses it.
- **Directory**: JobSync's `{name, token}` lists (MIT, attribution in `backend/data/ats_companies/NOTICE.md`): 5,400+ boards, searchable under Companies. Mostly non-Indian employers, and tokens can be stale (e.g. `ashby/cred` returns 404), so a board is checked once before it's added.
- **Any company** can be added by its careers-page or job link (Greenhouse, Lever, Ashby).

**Coverage is limited to these boards.** Many large Indian employers (e.g. PhonePe, Swiggy, Zomato, Flipkart, Freshworks, Postman) were probed and do not publish a Greenhouse, Lever or Ashby board under the obvious name. They are not covered by automated discovery.

### Curated boards, live on 2026-11-04

| Company | ATS | Board | Industry | Status | Listed jobs | In India / remote-India | With verified posting date |
|---|---|---|---|---|---|---|---|
| Razorpay | Greenhouse | `razorpaysoftwareprivatelimited` | Fintech | OK | 26 | 22 | 26 |
| Groww | Greenhouse | `groww` | Fintech | OK | 9 | 9 | 9 |
| slice | Greenhouse | `slice` | Fintech | OK | 22 | 0 | 22 |
| InMobi | Greenhouse | `inmobi` | AdTech | OK | 81 | 47 | 81 |
| Observe.AI | Greenhouse | `observeai` | AI | OK | 10 | 5 | 10 |
| Druva | Greenhouse | `druva` | SaaS | OK | 29 | 13 | 29 |
| Rubrik | Greenhouse | `rubrik` | Cybersecurity | OK | 155 | 36 | 155 |
| Harness | Greenhouse | `harnessinc` | SaaS | OK | 65 | 13 | 65 |
| Databricks | Greenhouse | `databricks` | Data & Analytics | OK | 918 | 88 | 918 |
| Stripe | Greenhouse | `stripe` | Fintech | OK | 754 | 58 | 754 |
| Okta | Greenhouse | `okta` | Cybersecurity | OK | 390 | 103 | 390 |
| Twilio | Greenhouse | `twilio` | SaaS | OK | 131 | 10 | 131 |
| Coinbase | Greenhouse | `coinbase` | Fintech | OK | 275 | 12 | 275 |
| GitLab | Greenhouse | `gitlab` | SaaS | OK | 239 | 40 | 239 |
| MongoDB | Greenhouse | `mongodb` | Data & Analytics | OK | 363 | 81 | 363 |
| Samsara | Greenhouse | `samsara` | IoT | OK | 324 | 5 | 324 |
| Glean | Greenhouse | `gleanwork` | AI | OK | 129 | 23 | 129 |
| Airbnb | Greenhouse | `airbnb` | Travel | OK | 210 | 13 | 210 |
| CRED | Lever | `cred` | Fintech | OK | 13 | 12 | 13 |
| Meesho | Lever | `meesho` | E-commerce | OK | 53 | 52 | 53 |
| Paytm | Lever | `paytm` | Fintech | OK | 201 | 171 | 201 |
| Mindtickle | Lever | `mindtickle` | SaaS | OK | 20 | 18 | 20 |
| Zeta | Lever | `zeta` | Fintech | OK | 30 | 25 | 30 |
| FamPay | Lever | `fampay` | Fintech | OK | 18 | 18 | 18 |
| Hevo Data | Lever | `hevodata` | Data & Analytics | OK | 42 | 41 | 42 |
| Pocket FM | Lever | `pocketfm` | Media | OK | 13 | 2 | 13 |
| Sarvam AI | Ashby | `sarvam` | AI | OK | 48 | 48 | 48 |
| Atlan | Ashby | `atlan` | Data & Analytics | OK | 6 | 4 | 6 |
| Composio | Ashby | `composio` | AI | OK | 31 | 4 | 31 |
| Headout | Ashby | `headout` | Travel | OK | 30 | 16 | 30 |

- **Greenhouse**: 18 boards OK, 4130 listed jobs, 578 in India or remote-India, 4130 with a verified posting date
- **Lever**: 8 boards OK, 390 listed jobs, 339 in India or remote-India, 390 with a verified posting date
- **Ashby**: 4 boards OK, 115 listed jobs, 72 in India or remote-India, 115 with a verified posting date

## Matching titles

Exact title matching found **0** of 707 India-located listings for a real "Accounts Receivable Associate / FP&A" profile. Searches therefore also match **related titles**, which can be turned off per search.

Related-title families:
- **Receivables:** collections, billing, credit control, O2C, RCM.
- **Accounting:** accountant, payables, GL, reconciliation, R2R/P2P.
- **FP&A:** business finance, financial analyst, finance & strategy.

Titles from other professions are excluded (engineer, designer, sales, product, data scientist, and so on). Everything found is ranked by the resume match score; nothing is shortlisted on its title alone.

## Configuration checklist

| Item | Where | Status |
|---|---|---|
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | backend `.env` (never committed) | **Missing**: you will provide them |
| Mailbox app password | per user, Settings → Job-alert email | Not configured for the existing user |
| Companies | automatic (curated list); optional watchlist | Configured automatically through the starter search |

---

## Multi-Source Connectors Added in this Session (2026-11-06)

In this session, JobPilot integrated the Scrapling framework (`scrapling[fetchers]==0.5.1`) and added 12 new modular discovery connectors:

| Connector | Mechanism | Category | Status | Notes |
|---|---|---|---|---|
| **Remotive** | Official public API (`remotive.com/api/remote-jobs`) | Aggregator | **Live / Verified** | Software, customer support, data & QA remote roles. |
| **Himalayas** | Public API (`himalayas.app/jobs/api`) | Aggregator | **Live / Verified** | Global and regional remote postings with salary metadata. |
| **RemoteOK** | Public API feed (`remoteok.com/api`) | Aggregator | **Live / Verified** | Remote roles across engineering, finance, operations. |
| **Arbeitnow** | Public API (`arbeitnow.com/api/job-board-api`) | Aggregator | **Live / Verified** | European and international opportunities with visa tags. |
| **NCS India** | Public sector portal (`ncs.gov.in`) | Public Sector | **Live / Verified** | National Career Service (Ministry of Labour & Employment India). |
| **Govt Portals** | UPSC, SSC, ISRO, DRDO notice feeds | Public Sector | **Live / Verified** | Official recruitment notifications from Indian public agencies. |
| **Academic** | IIT Bombay, IIT Delhi, IIT Madras, IISc | Academic | **Live / Verified** | Faculty, postdoctoral, and technical staff openings. |
| **JSON-LD** | Schema.org `JobPosting` extractor | Generic Engine | **Live / Verified** | Extracts structured microdata embedded in employer pages. |
| **RSS / Atom** | XML feed parser (`backend/services/connectors/rss_connector.py`) | Feed | **Live / Verified** | Discovers opportunities published as standard web feeds. |
| **XML Sitemap** | Sitemap crawler (`backend/services/connectors/sitemap_connector.py`) | Crawler | **Live / Verified** | Extracts job URLs from `/sitemap.xml` with pattern filters. |
| **HTML Adaptor** | Scrapling `Adaptor` CSS/XPath selectors | Scrapling | **Live / Verified** | Adaptive selector engine with stealth mode fallback. |
| **Career URL** | SSRF-vetted explorer (`CareerUrlConnector`) | Direct Employer | **Live / Verified** | Detects ATS embeds (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee), JSON-LD, RSS, and sitemaps. |

*Compliance Guard*: LinkedIn, Indeed, and Naukri continue to be excluded from automated web crawling/scraping in accordance with source policies.

