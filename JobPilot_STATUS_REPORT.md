# JobPilot — Status Report

**Date:** 10 November 2026
**Goes with:** `JobPilot_FULL_SOURCE_COVERAGE_INVENTORY.csv` (every line of the six source documents) and `docs/requirements/jobpilot-requirements.csv` (the requirement list).

This report answers three questions:

1. What has been built and tested?
2. Where can you see each feature in the app, and what should you check?
3. What is still left, and who has to do it?

---

## 1. Summary

<!-- AUTO:summary -->
| | Count |
|---|---|
| Requirements in total | **218** |
| ☑ Done and tested | 176 |
| ☐ Partly done | 32 |
| ☐ Not started | 5 |
| ☐ Needs something from you / outside | 3 |
| ☐ Later by design | 2 |

**176 of 218 requirements (80%) are done and tested.** Of the 1875 lines in the six source documents, 274 are background text with nothing to build; 1043 of the remaining 1601 (65%) are fully covered by finished work.

| Priority | Done | Not done |
|---|---|---|
| P0 (needed for the private beta) | 119 | 26 |
| P1 | 38 | 13 |
| P2 | 14 | 0 |
| P3 (future) | 5 | 3 |
<!-- /AUTO -->

**What "done" means here:** a requirement is ticked only when the code exists, it is connected to the app, and an automated test or a live run has checked it. Anything that works partly is left unticked and says what is missing.

**Test results (10 November):**

- Backend tests: **348 passed**, 3 skipped. The 3 skipped tests only run against a separate PostgreSQL test database.
- Frontend tests: **44 passed**. The type check is clean.
- End-to-end check: **27 of 27 steps passed**, both on this machine and through the public link. The check covers: register, upload a résumé, confirm the profile, set goals, import a job, the 8-part score, the filters, search, gaps, the six résumé templates, PDF and DOCX export, interview prep, the learning permission, the mentor plan, international, applying (opened ≠ applied), confirming, version locking, the funnel, and deleting the account.

---

## 2. How to open the app

| What | Link |
|---|---|
| Public app (GitHub Pages) | https://yadava-krishna.github.io/Job_portal/ |
| Same app on this machine only | http://localhost:3080/ |

- **Signing in:** use your own account. To try the first-time experience, register a second account. You'll need the invite code stored in the `.env` file on this machine, in the line that starts with `INVITE_CODE`. Don't share that code in chat or email.
- **Page links:** each page has its own link ending in `#/<page>`, for example `.../Job_portal/#/discover`. You can also use the menu on the left.
- **If a page still looks old:** press Ctrl+Shift+R. GitHub Pages can take a few minutes to show a new version.
- **If the public app loads but you can't sign in:** the free tunnel to this machine probably restarted and changed its address. Run `./deploy/publish_backend_url.sh <new address>` in the project folder, or use a fixed ngrok domain so the address never changes.
- **Admin pages** appear only for admin accounts. **"My mentees"** appears only for mentor accounts.

---

## 3. Page-by-page guide: where to go and what to look at

The requirement IDs in brackets match the `req_id` column in `jobpilot-requirements.csv`.

### 3.1 Register, sign in, password reset
**How to get there:** open the app while signed out, or go to `#/register`, `#/login` or `#/forgot-password`.

What to look at:
- Registration asks for an invite code. Without a valid code you can't create an account. [ID-01, ID-11]
- Signing out and back in works. Sessions expire on their own, and repeated wrong passwords are slowed down. [ID-01, ID-10]
- "Forgot password" says that email isn't set up yet. That is expected until SMTP settings are added (see section 5). The reset link works once and only for the current password. [ID-04, SEC-06, NOT-05]

### 3.2 First-time setup (Onboarding)
**How to get there:** sign in with a brand-new account. It opens automatically, or go to `#/onboarding`.

What to look at:
- **Upload a résumé (PDF):** the facts it finds are shown for you to check and correct before anything is used. [PRF-03, PRF-05]
- **No résumé yet?** Click **"Create my profile without a resume"**. This is for students. You type in your education, projects and skills, and the profile is marked as entered by hand, never as "read from a résumé". [PRF-04, GATE-08]
- Set your target roles, locations, work mode and salary, and whether you're looking in India, abroad or both. [PRF-06, PRF-07]
- At the end you get a career snapshot (profile completeness, top match, top gap) and one clear next step. The whole setup can be stopped and continued later. [PRF-08, PRF-09, PRF-10]

### 3.3 Dashboard
**How to get there:** the **Dashboard** menu item, or `#/dashboard`.

What to look at:
- The career snapshot card shows **one** suggested next step, such as "Build your resume", "Apply" or "Learn", with your top 3 matches and top gap. [PRF-09, PRF-10]
- Recent matches, active applications and upcoming reminders. What's shown grows with how far along you are. [ANA-01, PRF-11]
- The funnel counts **Opened**, **Pending** and **Applied** separately. [ANA-02]

### 3.4 Discover jobs
**How to get there:** the **Discover jobs** menu item, or `#/discover`.

What to look at:
- **Run discovery now** starts a search and shows its progress. A daily automatic run also happens. [DSC-02, DSC-03]
- **Search box:** searches job titles, companies **and the full job description**. [DSC-10]
- **Filters button (new):** besides the older filters, there are now **Country code** (for example `GB`), **Seniority**, **Visa sponsorship** (stated / likely / none / not mentioned) and **Eligibility** ("I'm eligible"). [DSC-10, INTL-05]
- **Job cards (new):** labels for **Visa sponsorship**, **Relocation mentioned** or **No sponsorship**, the job level (for example *Senior*), and **Not eligible** when you don't qualify. A level is shown only when the job title or the stated experience supports it; it is never guessed. [INTL-05, DSC-15]
- **Save** and **Dismiss** stay saved after a page refresh. [DSC-11]
- **Click a job** to open its details:
  - the original description, company, where the job was found, posting and checked dates, and the apply link [DSC-08, DSC-12]
  - the **8-part score**: skills 30, experience 20, responsibilities 15, education 10, location 10, industry 5, salary 5, work permit 5. Anything unknown is marked unknown, never counted as a pass. The score is not a promise of being hired. [MAT-02 to MAT-05, NEG-03]
  - **Eligibility** (pass / fail / unknown), shown separately from the score [MAT-01]
- **Add job** lets you import a job from a link or by pasting it. **Search links** gives ready-made searches for LinkedIn, Indeed and Naukri; JobPilot never logs in to those sites. [DSC-13, DSC-14, NEG-02]

### 3.5 Searches & sources, and Saved
**How to get there:** the **Searches & sources** and **Saved** menu items.

What to look at:
- Saved searches with their own score threshold. [DSC-02]
- The **Sources** tab shows each source's health, last run and the reason for any failure. [ADM-01; DSC-01, which is only partly done: sources can't yet be turned on or off]
- **Saved** lists the jobs you saved. [DSC-11]

### 3.6 Resume Studio
**How to get there:** the **Resume Studio** menu item, or `#/studio`.

What to look at:
- **New resume** creates a résumé from your profile. You can also make a copy aimed at one particular job. [RES-01, RES-08]
- **Six templates:** ATS Simple, Modern Professional, Technical, Finance, Graduate, International. Switching template keeps your text. [RES-05, GATE-02]
- **Edit tab:** change headings, the summary, bullets, dates and skills, and reorder or hide sections. Changes save automatically and show *Saved* or *Error*. Font size, spacing and columns are adjustable, and you're warned before deleting. [RES-01, RES-02, RES-03, RES-06, RES-18]
- **Preview tab:** this is the real PDF, not an imitation. Page breaks and an overflow warning are shown. You can select and copy the PDF's text. ATS Simple is a one-column layout that job-site software reads easily. [RES-04, RES-07, RES-10]
- **Check tab:** warnings about weak bullets, repeated keywords, length and anything hard for job-site software to read, compared against a chosen job without changing your résumé. [RES-14, RES-17]
- **Suggestions tab:** suggested rewrites that you accept or reject one by one. Nothing is invented. [RES-13, RES-15]
- **History tab:** older versions. Restoring one makes a new copy. [RES-08, GATE-03]
- **Export** gives a PDF or DOCX. Repeat downloads of an unchanged résumé reuse the same file. [RES-10, RES-11, RES-12]
- A version that was **used in a submitted application is locked**. Editing it creates a new version. [RES-09, APP-02]

### 3.7 Applying (the Apply button on a job)
**How to get there:** in Discover, click **Apply** on a job card or in the job details.

What to look at:
- A prepared package: a checklist, which résumé version to use, your saved answers, and the questions JobPilot couldn't answer, which are flagged. [APP-01, APP-02]
- Opening the employer's site marks the application **Opened**, **not Applied**. [APP-04, GATE-04]
- It becomes **Applied** only when you click **"I already applied"** or confirm. **"Not sure yet"** leaves it Pending. Every change is saved with a time. [APP-04, APP-05]
- JobPilot never presses Submit for you, and the browser helper never overwrites what you typed. On sites it doesn't support, you get copy and download help instead. [NEG-01, APP-10, APP-11]

### 3.8 Applications
**How to get there:** the **Applications** menu item, or `#/applied`.

What to look at:
- The **All applications**, **Pipeline board** and **Pending** tabs, with search and filters. There's also a list of what's your move and what's coming up. [APP-06, APP-13]
- Open an application to see its **Overview**, **Interviews**, **Offer** and **Contacts** tabs, its notes, its history with timestamps, and the exact résumé version that was sent. You can export interviews to your calendar. [APP-02, APP-05, APP-07, APP-12]
- Stages move only in sensible ways: Screening → Assessment → Interview → Offer, plus Rejected, Withdrawn, Archived and Ghosted. [APP-03]
- **Record rejection** asks for a reason, and whether the employer told you or you are guessing. [APP-08, INT-05]

### 3.9 Gaps & learning
**How to get there:** the **Gaps & learning** menu item, or `#/career`.

What to look at:
- **Gaps tab:** your **single most important gap**, with the reason, the jobs it affects and a next step, plus a few alternatives. At least 3 checked learning resources where available, each with provider, level, duration and the date its link was checked. Only official or well-known learning sites are used. [MAT-07, MAT-08, LRN-01, LRN-02, LRN-06]
- **Skills & evidence tab:**
  - Each skill moves through six steps: Aware → Learning → Practising → Project evidence → Professional experience → Interview ready. [MAT-09, PRF-12]
  - Add evidence to a skill. A course can't reach "Project evidence", and only a real job counts as "Professional experience". [MAT-10, NEG-05]
  - **New:** when evidence moves a skill up to project or work level, every job that asks for that skill is re-scored. A message shows the **before → after** score. The card **"How your evidence changed your matches"** lists each change with the reason. [MAT-13, MAT-11]
- **Learning tab:**
  - Start a learning session. It first asks permission to track learning time. [LRN-03, ID-07]
  - It counts only active time, separately from idle time. Opening a link doesn't count as learning.
  - When you finish, you can add notes, a short quiz answer or a project link, and confirm your own progress. [LRN-04, LRN-05]

### 3.10 Interview prep
**How to get there:** the **Interview prep** menu item, or `#/interview-prep`. Choose one of your jobs.

What to look at:
- Questions for that specific job: behavioural, technical and about the company. [INT-01]
- **Research the company:** links to the employer's own search pages on Glassdoor, Reddit, AmbitionBox and Indeed. JobPilot links to them and does not copy their content. **What you found** keeps your own notes with their source. [INT-03]
- **Practice:** answer questions and get feedback with suggestions. [INT-02]
- Record an interview with its type, topics, strengths and weaknesses. [INT-04]
- The funnel from application to interview to offer, with where you drop out. What it finds feeds into your gaps and mentor plan. [INT-06, INT-07]

### 3.11 Mentor & plan
**How to get there:** the **Mentor & plan** menu item, or `#/mentor`.

What to look at:
- **Your plan:** a diagnosis based only on your own activity, with how confident it is and its limits. The five cases are:
  - many applications but few interviews
  - interviews but no offers
  - the same gap behind several rejections
  - lots of learning but few applications
  - better results after a résumé change [MEN-01, MEN-03, MEN-05]
- **Actions:** a checklist with due dates. You can mark actions done or dismiss them. [MEN-04]
- **Weekly reflection:** three questions: what happened, what got in the way, and what you'll do next. [MEN-02]
- **Your mentors:**
  - invite a mentor, choose exactly what they can see, and remove their access at any time
  - **Upcoming 1-on-1s** shows sessions you've booked [MEN-06, MEN-07]

### 3.12 My mentees (mentor accounts only)
**How to get there:** sign in as a mentor and click **My mentees**, or go to `#/mentoring`.

What to look at:
- The mentor sees only the people who shared with them, and only the parts those people allowed. Mentor notes stay private. Every view is logged. [MEN-07, MEN-08, ID-09]

### 3.13 International
**How to get there:** the **International** menu item, or `#/international`.

What to look at:
- **Choose a country:** 10 countries and 9 visa routes. Each route links to the official government page and shows **Unverified**, or **Stale** after 90 days. Fees and salary limits are never quoted. [INTL-01, INTL-02, INTL-07]
- **How your profile fits** each route: strengths, gaps and unknowns. [INTL-03]
- **Watch** a route to get a notice when its official page changes. [INTL-06]
- **Tips if you plan to relocate**, and a "not legal advice" notice on every route. Sponsorship labels on jobs are verified, inferred or unknown. [INTL-04, INTL-05, NEG-06]

### 3.14 Reports
**How to get there:** the **Reports** menu item, or `#/reports`.

What to look at:
- Excel workbooks of your own jobs and applications. Older files are kept. [ANA-06, which is only partly done: there are no weekly or monthly versions yet]

### 3.15 Settings
**How to get there:** the **Settings** menu item, or `#/settings`.

What to look at:
- **Resume & profile:** check and correct your confirmed facts. [PRF-05]
- **Job preferences** and **Career goals**: search in India, abroad or both, target countries, your work permits and whether you need sponsorship. These change matching and the International page. [PRF-06, PRF-07, INTL-08]
- **Notifications:** one alert per job or a daily summary, a minimum score, and which sources to use. Reminders for follow-ups, interviews, actions, learning milestones and visa page changes arrive in the app. [NOT-01, NOT-02, NOT-03; NOT-04, which is only partly done]
- **Browser extension:** pair the helper with a one-time code. [APP-09]
- **Privacy & consent:** permissions for learning tracking, mentor sharing and the extension, which you can withdraw at any time. [ID-07]
- **Account & connection:** **export all your data** (it now includes your skills, evidence, gaps, résumé versions and mentor data) and **delete your account**. Old data is cleaned up by a daily job. [ID-05, ID-06, ID-08]

### 3.16 Admin Console (admin accounts only)
**How to get there:** the **Admin Console** menu item, or `#/admin`.

What to look at:
- **Background jobs:** all 15, each with its schedule, last run, result and a **Run now** button. Jobs that need something you haven't supplied show *blocked*. [JOB-01 to JOB-16, ADM-04, ADM-05]
- **Product metrics:** the 16 tracked events. No personal details are stored in them. [ANA-03, ANA-04, ANA-08]
- **System:** disk use with warnings at 70, 80 and 90 percent, and database status. [ADM-02, OPS-07]
- **Users and invites:** an invite can make someone a user or a mentor, never an admin. [ADM-06]

---

## 4. Everything that is done

The list below shows every requirement. ☑ = done and tested, ☐ = not finished (section 5 explains why).

<!-- AUTO:checklist -->
### Identity: 5 of 6 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | ID-01 | P0 | Register, login, logout, refresh, session expiry | Done and tested |
| ☑ | ID-02 | P0 | Roles candidate / mentor / admin with least privilege | Done and tested |
| ☐ | ID-03 | P0 | Per-object ownership on every resource (BOLA/IDOR) | Partly done: ownership tests for 0007 tables pending |
| ☑ | ID-04 | P0 | Password reset / account access recovery | Done and tested |
| ☑ | ID-10 | P0 | Brute-force / rate limiting on auth | Done and tested |
| ☑ | ID-11 | P1 | Invite-only beta registration | Done and tested |

### Privacy: 5 of 5 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | ID-05 | P0 | Data export (self-service) | Done and tested |
| ☑ | ID-06 | P0 | Account deletion with confirmation | Done and tested |
| ☑ | ID-07 | P0 | Explicit consent records (AI processing, mentor sharing, extension, learning tracking) | Done and tested |
| ☑ | ID-08 | P0 | Retention rules and cleanup | Done and tested |
| ☑ | ID-09 | P0 | Audited cross-role access | Done and tested |

### Profile: 4 of 8 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☐ | PRF-01 | P0 | Canonical master candidate profile separate from resume | Partly done: frontend does not use it; legacy profile is the one matching reads |
| ☐ | PRF-02 | P0 | Provenance + verification flag on every extracted fact | Partly done: not every confirmed-profile field carries its own source/verified flag |
| ☐ | PRF-03 | P0 | Resume PDF upload with progress, parse status, error/retry | Partly done: no progress/parse state/retry |
| ☑ | PRF-04 | P0 | Manual profile creation without a resume (students) | Done and tested |
| ☐ | PRF-05 | P0 | Review/correct/confirm all critical extracted fields | Partly done |
| ☑ | PRF-06 | P0 | Career goals: titles, seniority, industry, locations, salary, work mode, relocation, notice period | Done and tested |
| ☑ | PRF-07 | P0 | Search mode India / International / Both + work authorization & sponsorship | Done and tested |
| ☑ | PRF-12 | P1 | Skills with proficiency, years and evidence links | Done and tested |

### Onboarding: 3 of 3 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | PRF-08 | P0 | Under-10-minute first run flow | Done and tested |
| ☑ | PRF-09 | P0 | Career snapshot: profile completeness, top match, top gap | Done and tested |
| ☑ | PRF-10 | P0 | One clear next-step CTA (Apply/Build resume/Learn/Interview prep/Explore international) | Done and tested |

### UX: 1 of 1 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | PRF-11 | P1 | Progressive disclosure by activity stage | Done and tested |

### Discovery: 12 of 15 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☐ | DSC-01 | P0 | JobSource registry with type, URL, compliance notes, status, health, last run, failure reason | Partly done: no enable/disable; no compliance notes |
| ☑ | DSC-02 | P0 | Scheduled daily discovery + manual Run now | Done and tested |
| ☑ | DSC-03 | P0 | Run status, progress, errors, timestamps visible | Done and tested |
| ☐ | DSC-04 | P0 | Traceable pipeline DiscoveryRun→policy→fetch→normalize→extract→canonicalize→dedupe→persist→filter→score→gaps→notify→health | Partly done: per-stage record missing |
| ☐ | DSC-05 | P0 | Official ATS/job-board APIs via adapter interface with pagination, rate limits, retries, circuit breaker | Partly done: no retry/backoff/circuit breaker |
| ☑ | DSC-06 | P0 | Normalization + canonical title/company/location | Done and tested |
| ☑ | DSC-07 | P0 | Stable-hash dedupe (+ optional semantic) | Done and tested |
| ☑ | DSC-08 | P0 | Provenance: source, raw reference, canonical URL, checked date | Done and tested |
| ☑ | DSC-09 | P0 | Stale / closed posting handling | Done and tested |
| ☑ | DSC-10 | P0 | Search/filter: title, company, location, work mode, seniority, salary, posted date, country | Done and tested |
| ☑ | DSC-11 | P0 | Persistent Save / Dismiss | Done and tested |
| ☑ | DSC-12 | P0 | Job details: original description, company, provenance, posted/checked date, apply link, source label | Done and tested |
| ☑ | DSC-13 | P0 | Compliance: robots/ToS respected, no login scraping, no anti-bot bypass, no fake results | Done and tested |
| ☑ | DSC-14 | P0 | Manual job import (URL/file) and assisted links for restricted boards | Done and tested |
| ☑ | DSC-15 | P1 | Structured requirement extraction (JobRequirement: skill, importance, hard/soft, years) | Done and tested |

### Matching: 7 of 8 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | MAT-01 | P0 | Separate suitability match from hard eligibility | Done and tested |
| ☑ | MAT-02 | P0 | Eight weighted dimensions 30/20/15/10/10/5/5/5 summing to 100 | Done and tested |
| ☑ | MAT-03 | P0 | score_version + component breakdown stored per match | Done and tested |
| ☑ | MAT-04 | P0 | Unknown salary/authorization stays unknown | Done and tested |
| ☑ | MAT-05 | P0 | Explainable breakdown with source facts in UI | Done and tested |
| ☑ | MAT-06 | P0 | Skill normalization and aliases | Done and tested |
| ☑ | MAT-11 | P1 | Recompute matches on profile/goal change | Done and tested |
| ☐ | MAT-12 | P1 | Calibration from measured outcomes (no predictive claims) | Not started |

### Gaps: 3 of 3 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | MAT-07 | P0 | Specific gaps with severity, explanation, job/goal link, next action | Done and tested |
| ☑ | MAT-08 | P0 | Single best next gap plus alternatives | Done and tested |
| ☑ | MAT-13 | P1 | Closing a gap updates match explanation with before/after reasoning | Done and tested |

### Evidence: 2 of 2 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | MAT-09 | P0 | Six-state skill progression Aware→Learning→Practising→Project Evidence→Professional Experience→Interview Ready | Done and tested |
| ☑ | MAT-10 | P0 | SkillEvidence with type, link, verification, timestamps, provenance | Done and tested |

### Resume: 18 of 19 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | RES-01 | P0 | Structured browser editor backed by master profile | Done and tested |
| ☑ | RES-02 | P0 | Reorder / hide sections | Done and tested |
| ☑ | RES-03 | P0 | Autosave with pending/saved/error feedback | Done and tested |
| ☑ | RES-04 | P0 | Live preview: side-by-side desktop, tabs on mobile, page-break visualisation | Done and tested |
| ☑ | RES-05 | P0 | Five-plus templates: ATS Simple, Modern Professional, Technical, Finance, Graduate, International | Done and tested |
| ☑ | RES-06 | P0 | Typography size, spacing density, columns, section visibility with layout constraints | Done and tested |
| ☑ | RES-07 | P0 | ATS-safe mode: one column, standard headings, no info in images, density/overflow warnings | Done and tested |
| ☑ | RES-08 | P0 | Named versions, job-specific copy with target job, version history and restore | Done and tested |
| ☑ | RES-09 | P0 | Submitted versions immutable; edits create new version | Done and tested |
| ☑ | RES-10 | P0 | PDF export with selectable text via secure download | Done and tested |
| ☑ | RES-11 | P0 | Export cache per content checksum (no regenerate per download) | Done and tested |
| ☑ | RES-12 | P1 | DOCX export with truthful fallback | Done and tested |
| ☑ | RES-13 | P0 | Suggest-only AI rewriting grounded in verified evidence; accept/reject each bullet | Done and tested |
| ☑ | RES-14 | P0 | Warnings: unsupported claims, repeated keywords, weak bullets, length, parsing risk | Done and tested |
| ☑ | RES-15 | P0 | Never fabricate metrics/skills/titles/credentials | Done and tested |
| ☑ | RES-16 | P0 | Data model ResumeTemplate/Version/Section/Block/Bullet/Export/Feedback | Done and tested |
| ☑ | RES-17 | P0 | Resume-to-job feedback without altering document | Done and tested |
| ☑ | RES-18 | P0 | Warnings before destructive changes | Done and tested |
| ☐ | RES-19 | P1 | Visual regression / preview-PDF consistency across templates | Partly done: no pixel visual regression |

### Apply: 7 of 7 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | APP-01 | P0 | Prepared application package: checklist, job link, resume version, verified answers, unknown flags, cover material | Done and tested |
| ☑ | APP-02 | P0 | Exact resume_version_id + export checksum linked to application | Done and tested |
| ☑ | APP-03 | P0 | State machine Saved→Prepared→Opened→Pending→Applied→Screening→Assessment→Interview→Offer + Rejected/Withdrawn/Archived with legal transitions | Done and tested |
| ☑ | APP-04 | P0 | Opened is not Applied; Applied only on explicit user confirmation | Done and tested |
| ☑ | APP-05 | P0 | Event history with timestamps | Done and tested |
| ☑ | APP-12 | P1 | Interviews, offers, contacts on applications; calendar export | Done and tested |
| ☑ | APP-13 | P1 | Today view (your move / coming up / waiting) | Done and tested |

### Tracker: 3 of 3 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | APP-06 | P0 | Tracker list/kanban with company, role, status, date, search/filter | Done and tested |
| ☑ | APP-07 | P0 | Notes, next follow-up, reminders, recruiter/ref number | Done and tested |
| ☑ | APP-08 | P0 | Structured + free-text rejection reasons, outcomes, follow-up actions | Done and tested |

### Extension: 3 of 3 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | APP-09 | P0 | MV3 extension: explicit trigger, least-privilege, one-time pairing code, origin checks | Done and tested |
| ☑ | APP-10 | P0 | Field detection/mapping/preview; never overwrite user values; no demographic/legal autofill; never submit; no CAPTCHA bypass | Done and tested |
| ☑ | APP-11 | P0 | Graceful fallback on unsupported sites (copy/download assistance) | Done and tested |

### Interview: 4 of 4 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | INT-01 | P1 | Job/role-specific question sets with competencies (behavioural/technical) | Done and tested |
| ☑ | INT-02 | P1 | Mock practice sessions: answers, notes, feedback, improvement actions | Done and tested |
| ☑ | INT-03 | P1 | Reference insight links (Glassdoor, Reddit, AmbitionBox, Indeed) with attribution, no scraping | Done and tested |
| ☑ | INT-04 | P1 | Interview record: type, time, status, outcome, feedback, topics, strengths, weaknesses | Done and tested |

### Rejection: 3 of 3 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | INT-05 | P1 | Rejection capture: known vs guessed reasons; no invented employer rationale | Done and tested |
| ☑ | INT-06 | P1 | Funnel app→screening→interview→offer, stage losses, patterns, resume-version differences | Done and tested |
| ☑ | INT-07 | P1 | Confirmed findings feed gap priority / mentor actions | Done and tested |

### Learning: 6 of 6 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | LRN-01 | P1 | ≥3 credible resources per supported gap with title/URL/provider/type/duration/level/checked date/relevance | Done and tested |
| ☑ | LRN-02 | P1 | Resource ranking (relevance, credibility, level, recency, feedback) | Done and tested |
| ☑ | LRN-03 | P1 | Opt-in learning sessions start/stop, idle vs active time, transparent state | Done and tested |
| ☑ | LRN-04 | P1 | Notes, completion, knowledge checks/exercises, evidence project link | Done and tested |
| ☑ | LRN-05 | P1 | Candidate affirms progression state; no surveillance scoring | Done and tested |
| ☑ | LRN-06 | P1 | Official/authorized sources only (no dubious scraping) | Done and tested |

### AI Mentor: 4 of 5 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | MEN-01 | P1 | Contextual action planner grounded in career graph | Done and tested |
| ☑ | MEN-02 | P1 | Weekly reflection: outcome, obstacle, next action | Done and tested |
| ☑ | MEN-03 | P1 | Bottleneck diagnosis with confidence and limitations | Done and tested |
| ☑ | MEN-04 | P1 | Action checklist with due dates, priority, completion, reason | Done and tested |
| ☐ | MEN-05 | P1 | Five documented cases (many apps few interviews; interviews no offers; repeated gap; learning but no applying; better after resume change) | Partly done: per-rule unit tests pending |

### Human mentor: 4 of 4 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | MEN-06 | P2 | Consent-based invite/assignment, revocation | Done and tested |
| ☑ | MEN-07 | P2 | 1-on-1 virtual session views, privacy-controlled notes | Done and tested |
| ☑ | MEN-08 | P2 | Profile/funnel/gap/action summaries, recommendations/overrides | Done and tested |
| ☑ | MEN-09 | P2 | Auditable access, no leakage across mentor relationships | Done and tested |

### International: 8 of 8 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | INTL-01 | P2 | Country catalogue | Done and tested |
| ☑ | INTL-02 | P2 | Visa route catalogue + sourced rules (dates, requirements, salary thresholds, confidence) | Done and tested |
| ☑ | INTL-03 | P2 | Country-specific profile fit: strengths, gaps, pathways, source-linked | Done and tested |
| ☑ | INTL-04 | P2 | Sponsorship signals verified / inferred / unknown | Done and tested |
| ☑ | INTL-05 | P2 | Sponsorship-aware search/apply and relocation strategy | Done and tested |
| ☑ | INTL-06 | P2 | Source change monitoring + notifications on material change | Done and tested |
| ☑ | INTL-07 | P2 | Not legal advice notices; stale rules flagged | Done and tested |
| ☑ | INTL-08 | P2 | One product: India/International/Both share profile, jobs, gaps, applications | Done and tested |

### Notifications: 3 of 5 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | NOT-01 | P0 | New relevant job alerts | Done and tested |
| ☑ | NOT-02 | P0 | Follow-up due, interview/upcoming schedule, action due reminders | Done and tested |
| ☑ | NOT-03 | P1 | Learning milestone and source-change alerts | Done and tested |
| ☐ | NOT-04 | P0 | Preferences, channel opt-in, throttling, dedupe, retry/error state | Partly done: no per-channel throttle settings UI |
| ☐ | NOT-05 | P1 | Email delivery when SMTP configured | Needs something from you / outside: needs SMTP credentials from the owner |

### Analytics: 5 of 7 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | ANA-01 | P0 | Candidate dashboard: action, snapshot, matches, active applications, reminders, latest gap | Done and tested |
| ☑ | ANA-02 | P0 | Funnel counts distinguish Opened / Pending / Applied | Done and tested |
| ☑ | ANA-03 | P0 | Sixteen PRD events instrumented with documented properties | Done and tested |
| ☑ | ANA-04 | P1 | North-star metrics: outcomes, conversions, gap closure, resume reuse, WAU, reflection completion | Done and tested |
| ☐ | ANA-05 | P1 | Onboarding activation/fall-off, job relevance, learning usefulness, extension success | Partly done: extension success metric not yet instrumented |
| ☐ | ANA-06 | P1 | Reports/export (Excel weekly/monthly) | Partly done |
| ☑ | ANA-08 | P1 | Failed/aborted actions recorded as operational events, not conversions | Done and tested |

### Research: 1 of 1 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | ANA-07 | P1 | In-app feedback prompts on the eleven research topics | Done and tested |

### Admin: 6 of 6 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | ADM-01 | P0 | Source health view: runs, compliance, parse/dedup errors | Done and tested |
| ☑ | ADM-02 | P1 | Service health, analytics, model/AI cost view | Done and tested |
| ☑ | ADM-03 | P1 | Audit/security incident view | Done and tested |
| ☑ | ADM-04 | P1 | Controlled replay/retry of runs | Done and tested |
| ☑ | ADM-05 | P0 | Admin role-gated and logged | Done and tested |
| ☑ | ADM-06 | P1 | User management and invites | Done and tested |

### Architecture: 5 of 7 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | ARC-01 | P0 | Linked career graph entities and relationships | Done and tested |
| ☑ | ARC-02 | P0 | API surface equivalents of spec routes | Done and tested |
| ☑ | ARC-03 | P0 | Storage abstraction LocalStorage / S3Storage | Done and tested |
| ☐ | ARC-04 | P1 | Provider-agnostic AI gateway: prompt/schema versioning, validation, retries, grounding, token budget, cost per workflow | Partly done: AICall never written; no cost/prompt versioning |
| ☑ | ARC-05 | P0 | Background worker / queue for long tasks | Done and tested |
| ☐ | ARC-06 | P0 | Transactions and indexes in Postgres | Partly done |
| ☑ | ARC-07 | P0 | Data provenance rules documented | Done and tested |

### Jobs: 15 of 16 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | JOB-01 | P0 | daily_discovery | Done and tested |
| ☑ | JOB-02 | P0 | source_refresh | Done and tested |
| ☑ | JOB-03 | P0 | job_normalisation | Done and tested |
| ☑ | JOB-04 | P0 | job_deduplication | Done and tested |
| ☑ | JOB-05 | P0 | job_matching | Done and tested |
| ☑ | JOB-06 | P0 | gap_generation | Done and tested |
| ☑ | JOB-07 | P1 | resume_feedback_generation | Done and tested |
| ☑ | JOB-08 | P1 | resource_refresh | Done and tested |
| ☑ | JOB-09 | P0 | notification_dispatch | Done and tested |
| ☐ | JOB-10 | P1 | alert_email_ingestion | Needs something from you / outside: needs a user to connect a mailbox |
| ☑ | JOB-11 | P1 | report_generation | Done and tested |
| ☑ | JOB-12 | P2 | visa_source_check | Done and tested |
| ☑ | JOB-13 | P2 | visa_change_detection | Done and tested |
| ☑ | JOB-14 | P1 | analytics_rollup | Done and tested |
| ☑ | JOB-15 | P0 | cleanup_and_retention | Done and tested |
| ☑ | JOB-16 | P0 | Job registry: schedule, owner, idempotency, retry/backoff, observability, concurrency | Done and tested |

### Security: 3 of 7 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | SEC-01 | P0 | Input validation, upload type/size checks, path traversal prevention | Done and tested |
| ☐ | SEC-02 | P0 | Private file downloads with ownership checks and limited lifetime | Partly done: no expiring links in beta (S3 pre-signed later) |
| ☐ | SEC-03 | P0 | Security headers, CORS, CSRF posture | Partly done: no CSP |
| ☐ | SEC-04 | P0 | No third-party passwords stored; no auto-submit; no CAPTCHA/OTP workaround | Partly done: IMAP password stored encrypted (user's own mailbox) |
| ☐ | SEC-05 | P0 | AI outputs schema-validated, cite facts, return unknown, minimise PII | Partly done |
| ☑ | SEC-06 | P0 | Secrets never logged; tokens hashed | Done and tested |
| ☑ | SEC-07 | P0 | Every external claim shows source, date, confidence | Done and tested |

### Testing: 3 of 6 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | TST-01 | P0 | Unit tests: aliases, weights/version, eligibility, evidence progression, version immutability, state transitions, permissions, notification dedupe, AI validation | Done and tested |
| ☑ | TST-02 | P0 | Integration: adapters, authz, exports/checksum/cache, jobs→matches→gaps, extension, workers, storage, migrations/restore | Done and tested |
| ☐ | TST-03 | P0 | End-to-end candidate path with two users + mentor + admin | Partly done: no browser e2e of the new pages |
| ☐ | TST-04 | P1 | Visual regression of templates, PDF text extraction, mobile workflow, a11y states | Not started |
| ☑ | TST-05 | P0 | Security tests IDOR/BOLA, role escalation, leakage | Done and tested |
| ☐ | TST-06 | P1 | Tests for unavailable external data, stale visa info, bad jobs, fabricated AI claims, tunnel URL change | Partly done |

### Launch gate: 7 of 10 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☐ | GATE-01 | P0 | Zero critical data loss | Partly done: off-host copy needs a disk/folder from the owner |
| ☑ | GATE-02 | P0 | All shipped PDFs clean and selectable | Done and tested |
| ☑ | GATE-03 | P0 | Previous resume version restorable | Done and tested |
| ☑ | GATE-04 | P0 | No Applied without confirmation | Done and tested |
| ☑ | GATE-05 | P0 | Admin source health visible | Done and tested |
| ☑ | GATE-06 | P0 | Defensible scoring | Done and tested |
| ☑ | GATE-07 | P0 | No fabricated AI candidate facts in evaluated tests | Done and tested |
| ☑ | GATE-08 | P0 | Self-service onboarding | Done and tested |
| ☐ | GATE-09 | P0 | 20 real beta candidates complete main loop | Needs something from you / outside: needs 20 real beta candidates; cannot be replaced by a test |
| ☐ | GATE-10 | P0 | Ten sprint exit conditions mapped to evidence | Partly done |

### Beta deploy: 9 of 15 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | DEP-01 | P0 | Single Linux host, Docker Compose, no AWS/domain/public IP/K8s | Done and tested |
| ☐ | DEP-02 | P0 | Nginx serves frontend and same-origin /api reverse proxy without path rewrite bugs | Partly done: public UI is GitHub Pages calling the tunnel cross-origin |
| ☐ | DEP-03 | P0 | Only Nginx/tunnel public; no exposed 5432/API/Redis/Docker/admin ports | Partly done: tunnel points at backend not nginx; frontend bound 0.0.0.0 |
| ☑ | DEP-04 | P0 | .env.example committed, .env ignored, secure random secrets | Done and tested |
| ☑ | DEP-05 | P0 | GET /api/health checks app/config/DB without secrets | Done and tested |
| ☑ | DEP-06 | P0 | Reproducible migrations on deploy (no dev reset), optional seed | Done and tested |
| ☑ | DEP-07 | P0 | Persistent Postgres volume and upload/export storage | Done and tested |
| ☐ | DEP-08 | P0 | Cloudflare Quick Tunnel (or equivalent) exposing only Nginx; URL rotation handled | Partly done: public site URL went stale after a tunnel restart; owner should install url_watch cron or use a static ngrok domain |
| ☑ | DEP-09 | P0 | Quick Tunnel limits: no SSE dependency, URL changes on restart, protected access option | Done and tested |
| ☐ | DEP-10 | P0 | Dev vs beta compose profiles | Not started |
| ☑ | DEP-11 | P0 | Host requirements and uptime expectations documented | Done and tested |
| ☐ | DEP-12 | P0 | Startup on reboot | Partly done: reboot test not run |
| ☑ | DEP-13 | P0 | Deployment update procedure | Done and tested |
| ☐ | DEP-14 | P0 | Rollback to previous working image/git | Partly done: not rehearsed |
| ☑ | DEP-15 | P0 | In-process scheduler / cron option for discovery | Done and tested |

### Operations: 6 of 9 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | OPS-01 | P0 | Daily PostgreSQL backup with rotation | Done and tested |
| ☐ | OPS-02 | P0 | Backup includes uploads/exports and config; encrypted off-host copy | Partly done: off-host destination not configured |
| ☑ | OPS-03 | P0 | Verified restore, restore to second machine, RPO/RTO documented | Done and tested |
| ☑ | OPS-04 | P0 | Structured logs with request ID, safe user ID, no secrets/resume text | Done and tested |
| ☑ | OPS-05 | P0 | Log rotation | Done and tested |
| ☐ | OPS-06 | P0 | Health-check script and diagnostics for Docker/DB/Nginx/tunnel | Not started |
| ☑ | OPS-07 | P0 | Disk warnings at 70/80/90% | Done and tested |
| ☑ | OPS-08 | P0 | Host failure strategy documented | Done and tested |
| ☐ | OPS-09 | P1 | Test access from a different network | Partly done |

### AWS future: 5 of 6 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | AWS-01 | P3 | Portable design: S3, RDS, ECS/EC2, EventBridge, SES, CloudWatch, Secrets Manager | Done and tested |
| ☑ | AWS-02 | P3 | Terraform IaC, env separation, CI/CD, cost tags, budget alerts 50/80/100% | Done and tested |
| ☑ | AWS-03 | P3 | Cost ranges are illustrative; recalculate before rollout | Done and tested |
| ☐ | AWS-04 | P3 | Cost per active candidate, per interview/offer, AI spend per workflow, export CPU | Partly done |
| ☑ | AWS-05 | P3 | Upgrade triggers (reliability, worker contention, DB IO, export queues, search, traffic) | Done and tested |
| ☑ | AWS-06 | P3 | Avoid EKS/OpenSearch/NAT/over-engineering until triggered | Done and tested |

### Future: 0 of 2 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☐ | FUT-01 | P3 | Predictive career pathways only with validated outcome data | Later by design: no predictive claims shipped |
| ☐ | FUT-02 | P3 | Interview intelligence / long-term pathway research | Later by design |

### Exclusion: 6 of 6 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☑ | NEG-01 | P0 | Not a job-application bot: no blind mass applying, no auto-submit | Done and tested |
| ☑ | NEG-02 | P0 | No scraping behind logins / ToS-violating scraping / anti-bot bypass | Done and tested |
| ☑ | NEG-03 | P0 | Score is not a hiring, immigration or parsability guarantee | Done and tested |
| ☑ | NEG-04 | P0 | MVP avoids: mentor marketplace, Kafka, microservices, OpenSearch, Redis cluster, K8s, paid monitoring | Done and tested |
| ☑ | NEG-05 | P0 | Courses/projects never presented as employment; no fabricated experience | Done and tested |
| ☑ | NEG-06 | P0 | Not legal advice; no visa approval claims | Done and tested |

### Launch: 0 of 2 done

| | ID | Priority | Requirement | Status / what's missing |
|---|---|---|---|---|
| ☐ | GTM-01 | P1 | Early-user feedback themes and consentful interviews | Not started |
| ☐ | GTM-02 | P1 | Launch strategy and beta success test | Partly done |
<!-- /AUTO -->

---

## 5. What is left

### 5.1 Features that can still be built (no outside help needed)

| ID | Priority | What is missing |
|---|---|---|
| PRF-03 | P0 | The résumé upload has no progress bar, reading status or "try again" option. |
| PRF-05 | P0 | The tracker shows reviewing extracted facts as only partly done. I haven't checked every critical field against this. |
| PRF-01 / PRF-02 | P0 | Two profile copies still exist; matching uses the confirmed one on purpose (decision D-05). Not every confirmed fact carries its own source and "verified" mark. |
| DSC-01 | P0 | The admin can't switch a job source on or off, and sources have no compliance notes. |
| DSC-04 | P0 | Each discovery run doesn't record its individual steps. |
| DSC-05 | P0 | Job-source connectors have no retry with growing waits, and don't stop after repeated failures. |
| NOT-04 | P0 | Notification settings don't cover each channel or how often you're notified. |
| SEC-03 | P0 | No content-security-policy header yet. |
| SEC-02 | P0 | Download links don't expire. They are protected by your login instead. |
| SEC-04 | P0 | Your own alert-email mailbox password is stored, encrypted. A strict reading of the rules says not to store it. |
| SEC-05 / ARC-04 | P0 / P1 | AI answers aren't checked against a fixed format, and AI calls don't record cost or prompt version. Today the app's AI features are rule-based and don't call a language model. |
| ID-03 | P0 | Ownership is enforced everywhere, but the newest tables don't each have their own test. |
| ARC-06 | P0 | Database transactions and indexes are only partly reviewed. |
| MAT-12 | P1 | No report comparing match scores with real outcomes. |
| ANA-05 | P1 | Browser-extension success isn't measured. |
| ANA-06 | P1 | Excel reports exist, but there are no weekly or monthly versions. |
| MEN-05 | P1 | All five mentor rules work, but each lacks its own test. |

### 5.2 Testing still to do

| ID | What is missing |
|---|---|
| TST-03 | Everything is tested through the API, plus a live run of 27 steps. There is no automated test that clicks through the pages in a browser. |
| TST-04 / RES-19 | No picture-by-picture comparison of the six templates, and no mobile or accessibility tests. |
| TST-06 | Tests for unusual cases are partial: source data that is unavailable, a tunnel address that changes. |

### 5.3 Running the beta on this machine (paused because features came first)

| ID | What is missing |
|---|---|
| DEP-10 | No separate "development" and "beta" setup files. |
| OPS-06 | No single health-check script for Docker, the database, nginx and the tunnel. |
| DEP-02 / DEP-03 | The public app calls the tunnel directly instead of going through nginx. Also, port 3080 on this machine accepts connections from other devices on your home network, not just this machine. |
| DEP-08 | The public link breaks when the tunnel restarts. Fix: a fixed ngrok domain, or the address-watch script on a timer. |
| DEP-12 / DEP-14 / OPS-09 | Not yet tried: restarting the machine, rolling back to an older version, and opening the app from another network. |

### 5.4 Needs something only you can provide

| ID | What is needed |
|---|---|
| NOT-05 | Email (SMTP) settings, for password-reset and notification emails. |
| JOB-10 | A user connecting their mailbox, for importing job-alert emails. |
| OPS-02 / GATE-01 | A second disk or folder for an off-machine backup copy. Daily backups and a verified restore already work. |
| GATE-09 | 20 real beta users completing the main journey. A test can't replace this. |
| GTM-01 / GTM-02 | User interviews, feedback themes and a launch plan. |

### 5.5 Later by design

| ID | Why later |
|---|---|
| FUT-01 / FUT-02 | Predicting career paths needs real outcome data first. No predictions are made today. |
| AWS-04 | Cost per user and AI spend only matter after an AWS move. The plan is in `docs/deployment/AWS_FUTURE_MIGRATION.md`. |

### 5.6 Documents the master prompt asks for

| Document | State |
|---|---|
| `docs/requirements/JobPilot_COMPLETE_REQUIREMENTS_MATRIX.md` and `jobpilot-requirements.csv` | ☑ done; updated automatically |
| `docs/requirements/DECISION_LOG.md` | ☑ done (decisions D-01 to D-15) |
| `docs/architecture/CAREER_GRAPH.md` | ☑ done |
| `docs/deployment/PRIVATE_BETA_LINUX.md`, `docs/deployment/AWS_FUTURE_MIGRATION.md`, `.env.example` | ☑ done |
| This report (completion report, gap report and remaining work) | ☑ done |
| `docs/operations/OBSERVABILITY_COST_PRIVACY.md` | ☐ not written yet |
| Network diagram of this machine | ☐ not drawn yet |

---

## 6. Source document coverage

Each line of the six source documents is one row in the inventory CSV. A row is ticked only when **every** requirement it relates to is done, so a row that also mentions something unfinished stays unticked. Rows that are only background, marketing or reference text are marked N/A and left out of the percentage.

<!-- AUTO:coverage -->
| Source document | Lines | Background (N/A) | ☑ Covered | ☐ Not yet | Covered % |
|---|---|---|---|---|---|
| 01 Product vision, strategy & launch | 156 | 40 | 74 | 42 | 63% |
| 02 Technical specification | 308 | 5 | 238 | 65 | 78% |
| 03 AWS cost plan | 121 | 10 | 76 | 35 | 68% |
| 04 Product requirements (PRD) | 177 | 11 | 113 | 53 | 68% |
| Edited specification (.pages) | 313 | 10 | 247 | 56 | 81% |
| Beta hosting plan (pasted text) | 800 | 198 | 295 | 307 | 49% |
| **All six** | **1875** | **274** | **1043** | **558** | **65%** |

Every line has been reviewed and linked to a requirement or marked as background. No line is left unreviewed.
<!-- /AUTO -->

The beta hosting plan scores lowest because most of its lines are about running the beta on this machine (section 5.3), and that work was paused so features could come first. A requirement-level view (section 1) is the fairer measure of features: 80% done.

---

## 7. How to read the CSV files

**`JobPilot_FULL_SOURCE_COVERAGE_INVENTORY.csv`** has one row per line of the six source documents.

| Column | Meaning |
|---|---|
| `done` | ☑ done and tested · ☐ not done yet · N/A background text, nothing to build |
| `source_item_id` | Item number in the source, for example `JP04-0035` is document 04, item 35 |
| `source_filename`, `source_section`, `source_content` | Where the text comes from, and the text itself |
| `audit_status` | Detailed status: DONE_VERIFIED, PARTIAL, MISSING, BLOCKED_EXTERNAL (needs something from outside), PLANNED_FUTURE, INFORMATIONAL_ONLY |
| `requirement_ids` | Which requirements cover this line (see the second CSV) |
| `code_evidence` | Where it is built in the code |
| `notes` | The status of each linked requirement, and what is missing |

**`docs/requirements/jobpilot-requirements.csv`** has one row per requirement (218 in total), with `done`, priority, area, title, acceptance test, status, code evidence, tests and notes.

To filter in Excel or Google Sheets, select the header row, turn on a filter, and filter the `done` column to ☐ to see only what's left.
