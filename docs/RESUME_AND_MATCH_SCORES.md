# JobPilot scores: what each one measures

JobPilot shows three separate evaluations. They answer different questions, use different inputs, and are **never
averaged** into one number. None of them is an "ATS score" (no universal ATS score exists; every employer's system
reads resumes differently), and none predicts whether you will be shortlisted or hired.

| | Job Match | Resume Quality | Resume–Job Alignment |
|---|---|---|---|
| Question | Does *your verified profile* fit this job? | Is *this resume document* well built and readable? | Does *this resume* show what the job asks for? |
| Inputs | Confirmed profile, preferences, the job record | One saved revision: its exported PDF and its content | One saved revision's printed text, the job's listed skills, your verified profile |
| Changes when you edit a resume? | No | Yes | Yes |
| Changes when you pick another job? | Yes | No | Yes |
| Where | Job cards, job detail, Resume Studio → Check (with a job) | Resume Studio → Check | Resume Studio → Check (with a job) |

## Job Match (unchanged in V3.1)

`backend/services/scoring_v2.py`, version `v2.2026-11.2`. Eight weighted dimensions that add up to 100:
required skills 30, experience 20, responsibilities 15, education/certifications 10, location/work mode 10,
industry/domain 5, salary 5, work authorisation 5. A dimension with no data is *unknown*: it is left out and the other
weights are re-normalised, so missing information neither helps nor hurts. Eligibility (pass / fail / unknown) is
separate. Limitations: skills are matched against the job's extracted skill list; a short or vague posting gives a
less reliable score.

## Resume Quality

`backend/services/studio_service.py` (`feedback`) and `backend/services/resume_check.py`.

```
Resume Quality = max(0, 100 − 25 × must-fix − 8 × worth-fixing − 3 × suggestion)
```

* **Must-fix (error):** characters that print as boxes, text that can't be read back from the PDF, reversed dates,
  no name, no way to contact you, a render failure.
* **Worth-fixing (warning):** missing start dates, duplicate entries or bullets, very long bullets, figures not in
  your confirmed profile, a nearly empty last page or too many pages, emoji/symbols, an entry whose title or dates
  JobPilot's own reader pairs wrongly, a non-ATS-safe template.
* **Suggestion:** weak openings ("Responsible for…"), heavy keyword repetition.
* **Notes (info) count 0.** They used to cost 1 point each; V3.1 stops informational findings from lowering the score.
* **Job findings count 0 here:** job coverage is measured by Resume–Job Alignment instead.

The check always analyses one exact revision: the same exported PDF the preview shows (cached per content hash,
which includes the renderer version) and the same file Smart Apply attaches. The response carries `revision`,
`checksum` and `pages`; a check asked for an older revision is refused (HTTP 409) so a slow answer can never
replace a newer one. Every issue has a stable `id` (from what it is about, not list positions), the section, entry
and field, a severity, `why`, `evidence` and `fix`, and the editor's **Go to** opens that field. Issues with the
same cause on the same field are reported once.

Limitations: "read back" uses JobPilot's own PDF reader as a stand-in for an applicant-tracking system; real
systems differ. Writing checks are opinions, shown as suggestions.

## Resume–Job Alignment

`backend/services/resume_check.py` (`alignment`).

```
Alignment = 100 × (2 × required skills printed on this resume + 1 × preferred skills printed on this resume)
                 / (2 × required skills listed + 1 × preferred skills listed)
```

Only text printed on this resume version counts (skill synonyms such as "MS Excel" / "Excel" agree, through the
skills taxonomy). Each listed skill not on the resume is either **addable** (it is in your verified profile: the
Suggestions tab offers to add it, and shows roughly how much Alignment would change) or a **gap** (no evidence:
shown for honesty, never added for you). If the job lists no skills, Alignment is not measured.

## Why an 83% Job Match can sit next to a 58/100 Resume Quality

Job Match says your verified background fits the job. Resume Quality says how this particular document is built:
a resume with, say, one character that prints as a box (−25), a missing start date (−8) and a long bullet (−8) scores
59 however well you fit the role. Fix the document and Quality rises; Job Match stays the same because your profile
didn't change. Alignment then shows whether this resume actually puts the job's skills on the page.
