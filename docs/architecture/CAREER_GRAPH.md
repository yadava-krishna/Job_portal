# Career graph, API and worker contracts, data provenance

## The graph

```
User ─┬─ CandidateProfile (confirmed facts; legacy) ── CandidateProfileV2 (typed extras, provenance)
      ├─ JobPreference  = CareerGoal (titles, locations, salary, work mode, search mode India/International/Both,
      │                               target countries, work authorisation, sponsorship, seniority, relocation)
      ├─ CandidateSkill ── SkillEvidence (course, certificate, project, employment, …; links; learning session)
      ├─ UserJob = JobMatch (score_version, 8-dimension match_components, eligibility pass/fail/unknown)
      │     └─ Job ── JobRequirement (skill/education/experience, required/preferred, hard) ── JobSourceLink (provenance)
      ├─ Gap (from JobRequirements of relevant jobs + rejections) ── LearningResource ── LearningSession ── SkillEvidence
      ├─ ResumeVersion ── ResumeSection ── ResumeBlock ── ResumeBullet (evidence_refs, source, approved)
      │     ├─ ResumeExport (format, storage key, content checksum, file sha256)  └─ ResumeFeedback (per job)
      ├─ Application (status machine; resume_version_id + resume_export_id + resume_checksum; rejection reason/known)
      │     ├─ ApplicationEvent (every transition)  ├─ Interview (+ feedback: type, topics, strengths, weaknesses)
      │     ├─ Offer  └─ ApplicationContact
      ├─ InterviewPractice / InterviewInsight (attributed links and notes)
      ├─ Reflection (weekly outcome/obstacle/next action) ── MentorAction (ai_mentor | human_mentor | reflection | self)
      ├─ MentorAssignment (candidate-consented, scoped, revocable) ── MentorSession, MentorNote (shared/private)
      ├─ VisaWatch ── VisaRoute ── VisaRule ; Country
      ├─ Consent, Notification, AnalyticsEvent, UserFeedback
      └─ AuditLog (security and cross-role access)
DiscoveryRun / JobSource / SourceConnector / JobRun (background jobs) are operational records.
```

The chain the product promises — job requirement → gap → resource → evidence → resume bullet → exported version →
application → interview/outcome → reflection/action — is navigable through these foreign keys. Submitted
applications point at a **locked** resume version and the exact exported file hash; nothing later can change them.

## API map (spec 02 §18 → this codebase, prefix `/api/v1`)

| Spec | Here |
|---|---|
| POST /auth/register, login, logout | same |
| GET/PATCH /me/profile | GET/PUT /profile, GET/PUT /profile/master |
| GET/POST/PATCH /career-goals | GET/PUT /career-goals (+ /preferences for titles/locations/salary) |
| GET/POST /resumes, POST /resumes/:id/export | GET/POST /studio/versions, POST /studio/versions/{id}/export |
| GET /resume-templates[/:id] | GET /studio/templates |
| GET /jobs[/:id], POST /jobs/import | same |
| POST /discovery/run, GET /discovery/runs/:id | POST /jobs/discover, GET /jobs/runs/{id}; saved searches /discovery/searches/{id}/run |
| GET /jobs/:id/match | GET /jobs/{id}/analysis (dimensions, eligibility, score_version) |
| POST /matches/recompute | same |
| GET /gaps, GET /jobs/:id/gaps | same |
| GET /resources, POST /learning-sessions | same (+ heartbeat/pause/resume/complete) |
| POST/GET/PATCH /applications[/:id] | POST /applications/prepare, GET /applications[/{id}], stage/tracking/confirm/rejection |
| POST /interviews, POST /interviews/:id/feedback | POST /applications/{id}/interviews, POST /interviews/{id}/feedback |
| GET /mentor/plan, POST /mentor/reflection, actions | same (+ /mentoring/* candidate side, /mentor-workspace/* mentor side) |
| GET /countries, /visa-routes, /country-fit | same |
| GET /admin/source-health, /admin/metrics | GET /admin/sources, /admin/metrics, /admin/product-metrics, /admin/jobs, /admin/system |

## Background jobs
Registered in `backend/services/jobs_registry.py` (15 named jobs: schedule, owner, retries with backoff, run record
in `job_runs`, per-job lock against concurrent runs, admin replay). Jobs that depend on owner-supplied access record
`blocked` with the reason (e.g. `alert_email_ingestion` without any connected mailbox; e-mail delivery without SMTP).

## Provenance rules
1. Every candidate fact shown as verified comes from the candidate's confirmed profile or their own evidence entry.
   Parsed-but-unconfirmed data is never treated as verified; new skills start unverified.
2. Skill states only rise with evidence; courses/practice cap at *practising*, projects at *project evidence*,
   only employment at *professional experience*.
3. Resume bullets carry `source` (profile/user/suggestion) and `evidence_refs`; feedback flags figures that aren't in
   the confirmed profile. Suggestions are never applied automatically.
4. Jobs keep every source link with first/last seen and the posting-date source; "posted today" is shown only for
   verified dates. Sponsorship is `verified` only when the posting says so, `none` when it says it doesn't,
   `inferred` from relocation wording, otherwise `unknown`.
5. Unknown stays unknown: missing salary, country or authorisation is excluded from the score, never guessed.
6. External information (learning links, visa pages, interview references) shows its source and when it was last
   checked; visa routes are `unverified` until a person checks them and `stale` after their review date.
