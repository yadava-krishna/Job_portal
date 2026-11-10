# JobPilot — Global IT Job Discovery Source Catalogue

**Document Status:** Comprehensive Source Inventory & Compliance Matrix  
**Date:** November 2026  
**Total Identified Sources:** 115 Candidate Sources  
**Compliance Standard:** Strict Public Permission / No Unauthorized Scraping

---

## 1. Source Classification & Permission Framework

Every source in this catalogue is evaluated against strict legal, ethical, and technical compliance boundaries. Permissions are strictly categorized as:
- **Approved Public API:** Documented, open endpoints intended for public consumption without proprietary access keys or NDAs.
- **Approved Public Feed:** Standard syndication feeds (RSS 2.0, Atom 1.0, XML sitemaps) published for indexing and discovery.
- **Approved Public Page Access:** Permitted HTML/JSON-LD web crawling respecting `robots.txt` guidelines and reasonable rate limits ($\le 10$ req/min).
- **Permission Required / Partner API:** Commercial endpoints requiring employer partner agreements, private OAuth client credentials, or mutual NDAs.
- **Manual User-Provided:** Candidate-initiated import of job URLs, text clippings, or personal email alerts.
- **Blocked / Restricted:** Platforms where terms of service or technical access restrictions explicitly forbid automated harvesting (e.g. LinkedIn, Indeed, Naukri).

---

## 2. Verified Active Sources in JobPilot (Production Ready)

These 17 sources are currently integrated, tested, and actively functioning in the JobPilot codebase.

| Source ID | Name | Domain | Category | Access Method | Endpoint / Pattern | Rate Limit | Permission Status | Last Verified |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ats_greenhouse` | Greenhouse Public Board | `boards-api.greenhouse.io` | ATS Platform | Approved Public API | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | 30 req/min | Approved Public API | Nov 2026 |
| `ats_lever` | Lever Postings API | `api.lever.co` | ATS Platform | Approved Public API | `https://api.lever.co/v0/postings/{token}?mode=json` | 30 req/min | Approved Public API | Nov 2026 |
| `ats_ashby` | Ashby Job Board API | `api.ashbyhq.com` | ATS Platform | Approved Public API | `https://api.ashbyhq.com/posting-api/job-board/{token}` | 20 req/min | Approved Public API | Nov 2026 |
| `ats_smartrecruiters`| SmartRecruiters Public Postings| `api.smartrecruiters.com` | ATS Platform | Approved Public API | `https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100` | 20 req/min | Approved Public API | Nov 2026 |
| `ats_recruitee` | Recruitee Public Careers | `*.recruitee.com` | ATS Platform | Approved Public API | `https://{token}.recruitee.com/api/offers/` | 20 req/min | Approved Public API | Nov 2026 |
| `agg_remotive` | Remotive Tech API | `remotive.com` | Aggregator | Approved Public API | `https://remotive.com/api/remote-jobs?category=software-dev` | 10 req/min | Approved Public API | Nov 2026 |
| `agg_himalayas` | Himalayas Remote Jobs | `himalayas.app` | Aggregator | Approved Public API | `https://himalayas.app/jobs/api?limit=50` | 10 req/min | Approved Public API | Nov 2026 |
| `agg_remoteok` | RemoteOK JSON Feed | `remoteok.com` | Aggregator | Approved Public Feed | `https://remoteok.com/api` | 6 req/min | Approved Public Feed | Nov 2026 |
| `agg_arbeitnow` | Arbeitnow Public API | `arbeitnow.com` | Aggregator | Approved Public API | `https://www.arbeitnow.com/api/job-board-api` | 10 req/min | Approved Public API | Nov 2026 |
| `agg_adzuna` | Adzuna India API | `api.adzuna.com` | Aggregator | Approved Public API | `https://api.adzuna.com/v1/api/jobs/in/search/1` (Requires App ID/Key) | 10 req/min | Approved Public API (Keyed) | Nov 2026 |
| `scrapling_jsonld`| Schema.org JobPosting Extractor| Domain specific | Career Page | Approved Public Page Access | Extracted `<script type="application/ld+json">` with `@type: JobPosting` | 10 req/min | Approved Public Page Access | Nov 2026 |
| `scrapling_rss` | RSS/Atom Vacancy Feeds | Domain specific | Feed / Career | Approved Public Feed | Extracted `item` / `entry` elements with `<title>`, `<link>` | 10 req/min | Approved Public Feed | Nov 2026 |
| `scrapling_sitemap`| XML Sitemap Job Discovery | Domain specific | Career Page | Approved Public Page Access | Extracted URLs matching `*career*`, `*job*`, `*opening*` | 10 req/min | Approved Public Page Access | Nov 2026 |
| `scrapling_html` | Generic HTML Career Extractor | Domain specific | Career Page | Approved Public Page Access | Adaptive Scrapling selector matching job cards and titles | 6 req/min | Approved Public Page Access | Nov 2026 |
| `gov_ncs` | National Career Service | `ncs.gov.in` | Government | Approved Public Page Access | Public technology job search listings | 6 req/min | Approved Public Page Access | Nov 2026 |
| `gov_central` | NIC / C-DAC Openings | `nic.in`, `cdac.in` | Government | Approved Public Page Access | Public career notification feeds and recruitment circulars | 6 req/min | Approved Public Page Access | Nov 2026 |
| `academic_tech` | IIT / IISc Project Positions | `iisc.ac.in`, `iitb.ac.in` | Academic | Approved Public Page Access | Public project staff and research software engineer openings | 6 req/min | Approved Public Page Access | Nov 2026 |

---

## 3. Candidate Source Catalogue (100 Additional Sources Evaluated)

The following 100 technology employer sources have been categorized across sectors. They are candidates for automated discovery via public ATS tokens, verified career page URLs, or syndication feeds.

### 3.1 Global Multinational Technology Corporations (MNCs)
*Discovery Route: Enterprise ATS detection (Workday / Taleo / SuccessFactors / Custom Public API) or verified public sitemaps.*

| # | Company Name | Domain | Primary Tech Focus | Candidate Access Method | Public Endpoint / Career URL | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Google | `careers.google.com` | Cloud, AI/ML, Systems | Custom Public API | `https://careers.google.com/api/v3/search/` | Requires verification |
| 2 | Microsoft | `careers.microsoft.com`| Azure, Windows, Enterprise | Custom Public API | `https://gcsservices.careers.microsoft.com/search/api/v1/search` | Requires verification |
| 3 | Amazon / AWS | `amazon.jobs` | Cloud, Distributed Systems | Custom Public API | `https://www.amazon.jobs/en/search.json` | Requires verification |
| 4 | Apple | `jobs.apple.com` | iOS, Hardware, Cloud | Custom Public Search | `https://jobs.apple.com/en-in/search` | Requires verification |
| 5 | Meta | `metacareers.com` | Social, AI, Infrastructure | Custom Public Search | `https://www.metacareers.com/jobs/` | Requires verification |
| 6 | IBM | `ibm.com` | Cloud, Mainframe, Quantum | Workday Integration | `https://ibm.wd5.myworkdayjobs.com/en-US/IBM_Careers` | Requires verification |
| 7 | Cisco | `jobs.cisco.com` | Networking, Security | Oracle Taleo / Custom | `https://jobs.cisco.com/jobs/SearchJobs` | Requires verification |
| 8 | Oracle | `oracle.com` | Databases, Cloud ERP | Oracle Cloud Recruiter | `https://eeho.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/` | Requires verification |
| 9 | SAP | `jobs.sap.com` | Enterprise Software | SAP SuccessFactors | `https://jobs.sap.com/search/` | Requires verification |
| 10 | Salesforce | `salesforce.com` | CRM, Cloud, PaaS | Workday Integration | `https://salesforce.wd1.myworkdayjobs.com/External_Career_Site`| Requires verification |

### 3.2 Global Product & SaaS Companies
*Discovery Route: Supported ATS connectors (Greenhouse / Lever / Ashby / SmartRecruiters).*

| # | Company Name | Domain | ATS Platform | Board Token / URL | Permission Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 11 | Atlassian | `atlassian.com` | SmartRecruiters | `SmartRecruiters: atlassian` | Approved Public API |
| 12 | Stripe | `stripe.com` | Custom / Greenhouse | `https://stripe.com/jobs` | Approved Public Page Access |
| 13 | Databricks | `databricks.com` | Greenhouse | `Greenhouse: databricks` | Approved Public API |
| 14 | Snowflake | `snowflake.com` | Greenhouse | `Greenhouse: snowflake` | Approved Public API |
| 15 | Twilio | `twilio.com` | Greenhouse | `Greenhouse: twilio` | Approved Public API |
| 16 | Shopify | `shopify.com` | SmartRecruiters | `SmartRecruiters: shopify` | Approved Public API |
| 17 | Elastic | `elastic.co` | Greenhouse | `Greenhouse: elastic` | Approved Public API |
| 18 | Cloudflare | `cloudflare.com` | Greenhouse | `Greenhouse: cloudflare` | Approved Public API |
| 19 | GitHub | `github.com` | Custom / Microsoft | `https://github.com/about/careers` | Approved Public Page Access |
| 20 | GitLab | `gitlab.com` | Greenhouse | `Greenhouse: gitlab` | Approved Public API |
| 21 | Canva | `canva.com` | Lever | `Lever: canva` | Approved Public API |
| 22 | Figma | `figma.com` | Greenhouse | `Greenhouse: figma` | Approved Public API |
| 23 | Notion | `notion.so` | Ashby | `Ashby: notion` | Approved Public API |
| 24 | Airtable | `airtable.com` | Greenhouse | `Greenhouse: airtable` | Approved Public API |
| 25 | Miro | `miro.com` | Greenhouse | `Greenhouse: miro` | Approved Public API |
| 26 | Asana | `asana.com` | Greenhouse | `Greenhouse: asana` | Approved Public API |
| 27 | Monday.com | `monday.com` | Greenhouse | `Greenhouse: monday` | Approved Public API |
| 28 | Zoom | `zoom.us` | Workday | `https://zoom.wd5.myworkdayjobs.com/Zoom` | Requires verification |
| 29 | Dropbox | `dropbox.com` | Greenhouse | `Greenhouse: dropbox` | Approved Public API |
| 30 | Box | `box.com` | Greenhouse | `Greenhouse: box` | Approved Public API |

### 3.3 Indian IT Services, Technology Consulting & SI Firms
*Discovery Route: XML Sitemaps, Public Careers RSS, or Custom Job Search Endpoints.*

| # | Company Name | Domain | Category | Discovery Approach | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 31 | Tata Consultancy Services (TCS) | `tcs.com` | IT Services | iBegin Public Careers | Requires verification |
| 32 | Infosys | `infosys.com` | IT Services | Career Portal XML / JSON | Requires verification |
| 33 | Wipro | `wipro.com` | IT Services | iCIMS / SuccessFactors | Requires verification |
| 34 | HCLTech | `hcltech.com` | IT Services | Public Job Listings Feed | Requires verification |
| 35 | Tech Mahindra | `techmahindra.com` | IT Services | Careers Search Portal | Requires verification |
| 36 | LTIMindtree | `ltimindtree.com` | IT Services | SuccessFactors API | Requires verification |
| 37 | Persistent Systems | `persistent.com` | Digital Engineering | SmartRecruiters / Custom | Requires verification |
| 38 | Mphasis | `mphasis.com` | Cloud & Cognitive | Public Careers Search | Requires verification |
| 39 | Coforge | `coforge.com` | Digital Solutions | Public Job Feed | Requires verification |
| 40 | Birlasoft | `birlasoft.com` | Enterprise IT | Public Careers Page | Requires verification |
| 41 | Hexaware Technologies | `hexaware.com` | Automation / Cloud | Public Careers Page | Requires verification |
| 42 | Sonata Software | `sonata-software.com`| Modernization | Public Careers Feed | Requires verification |
| 43 | Zensar Technologies | `zensar.com` | Digital Solutions | Public Careers Page | Requires verification |
| 44 | Cyient | `cyient.com` | Engineering & Tech | Public Job Portal | Requires verification |
| 45 | Tata Elxsi | `tataelxsi.com` | Embedded & Design | Public Job Listings | Requires verification |
| 46 | KPIT Technologies | `kpit.com` | Automotive Software | Public Careers Page | Requires verification |
| 47 | Mindgate Solutions | `mindgate.solutions` | Payments Tech | Public Careers Page | Requires verification |
| 48 | Nucleus Software | `nucleussoftware.com`| Banking Software | Public Careers Page | Requires verification |
| 49 | Intellect Design Arena | `intellectdesign.com`| Financial Tech | Public Careers Feed | Requires verification |
| 50 | Newgen Software | `newgensoft.com` | Low-Code / BPM | Public Careers Page | Requires verification |

### 3.4 Banking Technology, Fintech & Global Capability Centers (GCCs)
*Discovery Route: Enterprise ATS (Workday, Taleo, Greenhouse, Lever).*

| # | Company Name | Domain | Platform / ATS | Access Method | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 51 | JPMorgan Chase & Co. | `jpmorganchase.com` | Oracle Taleo | Public Search API | Requires verification |
| 52 | Goldman Sachs | `goldmansachs.com` | Custom Careers | Public Search API | Requires verification |
| 53 | Morgan Stanley | `morganstanley.com` | Taleo / Custom | Public Search API | Requires verification |
| 54 | Barclays India | `barclays.co.uk` | Taleo | Public Job Search | Requires verification |
| 55 | Deutsche Bank | `db.com` | Workday | Public Job Search | Requires verification |
| 56 | Wells Fargo India | `wellsfargo.com` | Workday | Public Job Search | Requires verification |
| 57 | Standard Chartered | `sc.com` | Taleo | Public Job Search | Requires verification |
| 58 | PayPal | `paypal.com` | Workday | Public Search API | Requires verification |
| 59 | Razorpay | `razorpay.com` | Greenhouse | `Greenhouse: razorpay` | Approved Public API |
| 60 | PhonePe | `phonepe.com` | Greenhouse | `Greenhouse: phonepe` | Approved Public API |
| 61 | CRED | `cred.club` | Lever | `Lever: cred` | Approved Public API |
| 62 | Pine Labs | `pinelabs.com` | Darwinbox / Custom | Public Careers Page | Requires verification |
| 63 | BharatPe | `bharatpe.com` | Lever | `Lever: bharatpe` | Approved Public API |
| 64 | Zerodha | `zerodha.com` | Internal / Public Page| `https://zerodha.com/careers` | Approved Public Page Access |
| 65 | Groww | `groww.in` | Lever | `Lever: groww` | Approved Public API |

### 3.5 Semiconductor, Hardware & Embedded Systems
*Discovery Route: Workday, SuccessFactors, or Sitemaps.*

| # | Company Name | Domain | Focus Area | Access Method | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 66 | Intel | `intel.com` | CPUs, Silicon, Architecture | Workday Public API | Requires verification |
| 67 | NVIDIA | `nvidia.com` | GPUs, AI Hardware, CUDA | Workday Public API | Requires verification |
| 68 | AMD | `amd.com` | Processors, Graphics | Taleo Public Search | Requires verification |
| 69 | Qualcomm | `qualcomm.com` | Mobile Silicon, 5G | Workday Public API | Requires verification |
| 70 | Texas Instruments | `ti.com` | Analog, Embedded Processing| Workday Public API | Requires verification |
| 71 | Broadcom | `broadcom.com` | Networking Silicon | Workday Public API | Requires verification |
| 72 | Arm | `arm.com` | Processor Architecture | Custom Search | Requires verification |
| 73 | MediaTek | `mediatek.com` | Wireless, SoC | SuccessFactors | Requires verification |
| 74 | NXP Semiconductors | `nxp.com` | Automotive, IoT Silicon | Workday Public API | Requires verification |
| 75 | Synopsys | `synopsys.com` | EDA, Silicon IP | SuccessFactors | Requires verification |

### 3.6 High-Growth Technology Startups & Scaleups (India & Global)
*Discovery Route: Supported ATS connectors (Greenhouse / Lever / Ashby).*

| # | Company Name | Domain | ATS Platform | Board Token / URL | Permission Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 76 | Postman | `postman.com` | Greenhouse | `Greenhouse: postman` | Approved Public API |
| 77 | Hasura | `hasura.io` | Lever | `Lever: hasura` | Approved Public API |
| 78 | BrowserStack | `browserstack.com` | SmartRecruiters | `SmartRecruiters: browserstack` | Approved Public API |
| 79 | Swiggy | `swiggy.com` | SmartRecruiters | `SmartRecruiters: swiggy` | Approved Public API |
| 80 | Zomato | `zomato.com` | Custom / Lever | `https://www.zomato.com/careers` | Approved Public Page Access |
| 81 | Urban Company | `urbancompany.com` | Greenhouse | `Greenhouse: urbancompany` | Approved Public API |
| 82 | Meesho | `meesho.com` | Lever | `Lever: meesho` | Approved Public API |
| 83 | InMobi | `inmobi.com` | Jobvite / Custom | Public Careers Page | Requires verification |
| 84 | Freshworks | `freshworks.com` | SmartRecruiters | `SmartRecruiters: freshworks` | Approved Public API |
| 85 | Zoho | `zoho.com` | Zoho Recruit (Public) | `https://www.zoho.com/careers/` | Approved Public Page Access |
| 86 | Dream11 | `dreamsports.group`| Greenhouse | `Greenhouse: dreamsports` | Approved Public API |
| 87 | Cars24 | `cars24.com` | Lever | `Lever: cars24` | Approved Public API |
| 88 | Delhivery | `delhivery.com` | Custom / Sitemaps | `https://www.delhivery.com/careers` | Approved Public Page Access |
| 89 | Zepto | `zeptonow.com` | Ashby | `Ashby: zepto` | Approved Public API |
| 90 | Lenskart | `lenskart.com` | Darwinbox / Lever | Public Careers Page | Requires verification |

### 3.7 Remote-First Global Engineering Organizations
*Discovery Route: Supported ATS (Ashby, Greenhouse, Lever, Recruitee).*

| # | Company Name | Domain | ATS Platform | Board Token / URL | Permission Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 91 | Automattic (WordPress) | `automattic.com` | Custom / Greenhouse | `Greenhouse: automattic` | Approved Public API |
| 92 | Buffer | `buffer.com` | Lever | `Lever: buffer` | Approved Public API |
| 93 | Basecamp / 37signals | `37signals.com` | Custom Public Page | `https://37signals.com/jobs` | Approved Public Page Access |
| 94 | Zapier | `zapier.com` | Greenhouse | `Greenhouse: zapier` | Approved Public API |
| 95 | Ghost Foundation | `ghost.org` | Custom / Feed | `https://ghost.org/careers/` | Approved Public Page Access |
| 96 | DuckDuckGo | `duckduckgo.com` | Greenhouse | `Greenhouse: duckduckgo` | Approved Public API |
| 97 | Sourcegraph | `sourcegraph.com` | Greenhouse | `Greenhouse: sourcegraph` | Approved Public API |
| 98 | Grafana Labs | `grafana.com` | Greenhouse | `Greenhouse: grafana` | Approved Public API |
| 99 | Supabase | `supabase.com` | Ashby | `Ashby: supabase` | Approved Public API |
| 100 | Vercel | `vercel.com` | Ashby | `Ashby: vercel` | Approved Public API |

---

## 4. Source Policy Enforcement Matrix

To ensure absolute adherence to ethical crawling and data privacy:
1. **Robots.txt Interpretation:** Every automated connector verifies `robots.txt` disallow paths using `protego` or Python's `urllib.robotparser`. If a career directory is disallowed, crawling halts immediately.
2. **Identification Headers:** All HTTP/Scrapling requests identify JobPilot transparently via:
   `User-Agent: JobPilot/1.0 (+https://github.com/yadava-krishna/Job_portal; job-discovery-bot)`
3. **No Circumvention:** The system never bypasses Cloudflare, AWS WAF, Akamai, CAPTCHAs, or anti-bot shields. If an endpoint blocks access (HTTP 403/429/503), the source is marked `Blocked` or `RateLimited` and scheduled for backoff.
4. **Data Retention:** Only structured public job postings (title, company, description, location, URL) are stored. No proprietary company confidential information is ingested.
