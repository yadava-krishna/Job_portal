# JobPilot: Multi-Source Discovery Architecture & Scrapling Integration

*Generated: 2026-11-06 (Session: Scrapling & Multi-Source Expansion)*

---

## 1. Executive Summary

JobPilot has been transformed from an ATS/email/clipper tool into a comprehensive, multi-source discovery engine. Leveraging **Scrapling 0.5.1**, JobPilot discovers legitimate, publicly accessible job opportunities across:
- **Direct Employer Career Portals** (via automatic ATS detection, Schema.org JSON-LD microdata, XML sitemaps, and RSS/Atom feeds).
- **Public Sector & Government Portals** (National Career Service NCS India, UPSC, SSC, ISRO, DRDO).
- **Academic & Research Institutions** (IIT Bombay, IIT Delhi, IIT Madras, IISc Bangalore).
- **Curated Global & Remote Aggregators** (Remotive, Himalayas, RemoteOK, Arbeitnow).

All discovery adheres strictly to the **Non-Negotiable Compliance Invariant**: LinkedIn, Indeed, and Naukri are never scraped or crawled; interactions with them remain strictly client-side assisted (via the browser extension, clipper bookmarklet, and private IMAP alert emails).

---

## 2. Core Architecture

```
                                  [ User / Scheduled Discovery ]
                                                │
                                                ▼
                                    [ discovery_service.py ]
                                                │
                      ┌─────────────────────────┴────────────────────────┐
                      ▼                                                  ▼
           [ ATS Board Fetchers ]                            [ Scrapling Connectors ]
       (Greenhouse, Lever, Ashby,                         (Remotive, Himalayas, RemoteOK,
     SmartRecruiters, Recruitee)                          Arbeitnow, NCS, Govt, Academic,
                      │                                    JSON-LD, RSS, Sitemap, Custom)
                      │                                                  │
                      │                                                  ▼
                      │                                      [ scrapling_client.py ]
                      │                                      - SSRF pre-flight check
                      │                                      - Token bucket rate limiter
                      │                                      - Robots.txt parsing cache
                      │                                      - Fetcher / StealthyFetcher
                      │                                                  │
                      └─────────────────────────┬────────────────────────┘
                                                │
                                                ▼
                                    [ normalization.py ]
                                    (Unified NormalizedJob)
                                                │
                                                ▼
                                  [ Deduplication & Ingestion ]
                                                │
                                                ▼
                                  [ User Matcher & Feed Ingest ]
```

---

## 3. Scrapling Client Implementation (`backend/services/scrapling_client.py`)

The Scrapling Client wraps `scrapling` version `0.5.1` with strict enterprise defenses:

### 3.1 Network & SSRF Defenses
Before any TCP connection is established, the client performs pre-flight DNS resolution using `socket.getaddrinfo()`. The destination IP is tested against forbidden ranges:
- Loopback addresses (`127.0.0.0/8`, `::1`)
- RFC 1918 Private IPv4 networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
- Unique Local IPv6 addresses (`fc00::/7`)
- Link-local addresses (`169.254.0.0/16`, `fe80::/10`)
- Cloud instance metadata service (`169.254.169.254`)
- Multicast and broadcast addresses

Attempts to connect to private or internal addresses trigger an immediate `SSRFProtectionError` without issuing any network packet.

### 3.2 Dual-Fetcher Strategy
1. **Standard Fast Fetcher (`Fetcher`)**: Built on `curl_cffi` for realistic HTTP/2 TLS browser impersonation with minimal memory footprint.
2. **Stealthy Headless Fetcher (`StealthyFetcher`)**: Powered by Patchright for Javascript-heavy or dynamic single-page application career sites. Runs in ephemeral, unprivileged browser instances.

### 3.3 Resource Caps & Politeness
- **Response Size Cap**: Maximum 25 MB per response to prevent memory exhaustion and compression bombs.
- **Token-Bucket Rate Limiter**: Independent token buckets per domain preventing server bans or excessive traffic.
- **Robots.txt Cache**: Complies with site-specific crawling guidelines using cached `urllib.robotparser` and `protego`.
- **Bounded Concurrency**: Maximum 4 concurrent async fetches managed via an in-process `asyncio.Semaphore`.

---

## 4. Connector Suite (`backend/services/connectors/`)

JobPilot features 12 modular connectors implementing `BaseConnector`:

| Connector | Source ID | Category | Target / Protocol |
|---|---|---|---|
| **Remotive** | `remotive` | Aggregator | REST API (`remotive.com/api/remote-jobs`) |
| **Himalayas** | `himalayas` | Aggregator | REST API (`himalayas.app/jobs/api`) |
| **RemoteOK** | `remoteok` | Aggregator | JSON Feed (`remoteok.com/api`) |
| **Arbeitnow** | `arbeitnow` | Aggregator | REST API (`arbeitnow.com/api/job-board-api`) |
| **NCS India** | `ncs_india` | Public Sector | Web portal parser (`ncs.gov.in`) |
| **Govt Portals** | `gov_india` | Public Sector | Recruitment feeds (UPSC, SSC, ISRO, DRDO) |
| **Academic** | `academic_india` | Academic | Premier institutes (IIT Bombay, Delhi, Madras, IISc) |
| **JSON-LD** | `generic_jsonld` | Microdata | Schema.org `JobPosting` extractor |
| **RSS / Atom** | `generic_rss` | Feeds | Standard RSS 2.0 and Atom XML parser |
| **XML Sitemap** | `generic_sitemap` | Sitemaps | Crawler with job URL regex filtering |
| **HTML Adaptor** | `generic_html` | Scrapling | Scrapling `Adaptor` CSS & XPath extraction |
| **Career URL** | `career_url` | Direct Employer | SSRF-vetted explorer with ATS auto-detection |

---

## 5. Database Schema Extensions (Migration `0004`)

Migration `0004_multi_source_discovery.py` introduced strictly additive schema elements:

### 5.1 New Tables
- **`source_connectors`**:
  - `source_id` (PK, String 64)
  - `name`, `domain`, `category`, `access_method`
  - `status`, `rate_limit_rpm`, `is_discoverable`
  - `last_success_at`, `last_error`, `jobs_discovered`
- **`user_career_urls`**:
  - `id` (PK), `user_id` (FK to users)
  - `url`, `company_name`, `detected_ats`, `ats_token`
  - `has_json_ld`, `discovered_feed_url`, `discovered_sitemap_url`
  - `status`, `last_checked_at`, `jobs_found`

### 5.2 Extended Job Columns
- `jobs.country`: ISO 3166-1 alpha-2 or normalized country name.
- `jobs.seniority`: Entry, Mid, Senior, Lead, Executive.
- `jobs.application_url`: Direct target URL for applying.
- `jobs.source_name`: Display name of the originating connector.
- `jobs.extraction_method`: API, JSON-LD, RSS, Sitemap, or HTML Adaptor.
- `jobs.extraction_confidence`: High (verified structured data) or Medium.
- `jobs.parser_version`: Schema version for reproducible parsing.

---

## 6. Frontend Controls & User Interfaces

1. **Career URL Submission Form (`CareerUrlForm.tsx`)**:
   - Allows users to enter any company careers link.
   - Automatically detects ATS embeds, Schema.org microdata, feeds, and sitemaps.
   - Displays real-time discovery count and diagnostic feedback.
2. **Multi-Source Status Panel (`SourcesPanel.tsx`)**:
   - Real-time directory of all 12 discovery connectors.
   - Live health indicator (`ok`, `degraded`, `failing`).
   - One-click connector testing button with instant response reporting.
3. **Today's Focus Dashboard (`TodayView.tsx`)**:
   - Actionable agenda dividing tasks into "Your Move", "Coming Up", and "Waiting On Them".
4. **Interview & Offer Management (`AppliedPage.tsx`)**:
   - Full schedule tracker with `.ics` calendar export.
   - Offer breakdown recorder (salary, bonus, equity, deadlines).
   - Recruiter and contact directory.
5. **Admin Console (`AdminPage.tsx`)**:
   - System-wide metrics, user status controls, invite generator, and audit trail.

---

## 7. Testing & Quality Assurance

The multi-source discovery framework is verified with 100% test pass rates:
- `tests/api/test_scrapling_client.py`: Unit tests verifying SSRF address blocking, rate limiting, and response size capping.
- `tests/api/test_connectors.py`: Integration tests validating parser accuracy against fixture responses for Remotive, Himalayas, JSON-LD, and RSS feeds.
- `tests/api/test_admin.py`: RBAC security and administrative action testing.
- `tests/api/test_achievements.py`: Milestone badges and nickname generation.
- Full pytest suite: 121+ backend tests passing.
- Vitest suite: 30 frontend tests passing.
- Frontend production build: `tsc -b && vite build` passing with zero errors.
