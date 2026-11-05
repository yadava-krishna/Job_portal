# Platform support

Verified on 2026-11-05 against live public application forms, filled with **fabricated** test data and **never
submitted**: every write request to the platforms was blocked during the test, and none was a submission.

| | Greenhouse | Lever | Ashby |
|---|---|---|---|
| Pages | `job-boards.greenhouse.io/<board>/jobs/<id>`, `/embed/job_app?for=<board>&token=<id>`, also as an iframe on employer sites | `jobs.lever.co/<company>/<id>/apply` (+ EU) | `jobs.ashbyhq.com/<company>/<id>/application` (also embedded) |
| Name, e-mail, phone | first/last name by id; phone (country-format widget accepted) | full name, e-mail, phone | full name, e-mail, phone |
| Location | async location search: picked only when exactly one suggestion matches your location | text field (pick from Lever's suggestions yourself if shown) | text or combobox |
| Current company / title | when asked as a question | "Current company" field | when asked |
| Links | LinkedIn/website questions | LinkedIn, GitHub, Portfolio, Other. Twitter, Naukri and others are skipped (not in your profile) | LinkedIn/portfolio questions |
| Education | School (exact match only) and Degree (B.Com → "Bachelor's Degree" etc. is a *suggestion* to review). Later entries, field of study and dates: you | when asked as text | when asked |
| Dropdowns | react-select comboboxes: exact or single unambiguous option only | native selects, radios, checkboxes | radios, checkboxes, Yes/No buttons, comboboxes |
| Custom questions | `question_<id>` with labels | cards with the question text in the label block | `[data-field-path]` entries with titles |
| Number ranges ("16 to 30 days", "4.1 years and above", "7.1 LPA and above") | matched when your answer falls in exactly one range | same | same |
| Resume | attached to `#resume` on your click | **attach first**: Lever reads the resume and may fill fields itself; Fill then keeps those values unless you choose overwrite | attached to the Resume question; the separate "Autofill from resume" box is never used |
| EEO / demographic questions | never filled | never filled (detected by label or by options such as Male/Female) | never filled |
| CAPTCHA | reCAPTCHA Enterprise: yours to complete at submit | hCaptcha: yours | reCAPTCHA: yours |
| Live check results | 4 filled (first and last name, e-mail, phone), 2 custom questions need you, EEO and country skipped | 9 filled, 1 to review, 5 need you | 6 filled, 1 to review, 4 need you |

## Not supported

- **Employer-hosted application forms** (for example Stripe, Databricks and Okta careers sites) and other ATS such as
  Workday, SuccessFactors or iCIMS. The extension says "Not an application page". For Greenhouse jobs, JobPilot
  offers the Greenhouse-hosted form when Greenhouse actually serves it for that job (checked live, never guessed).
- **LinkedIn, Indeed, Naukri, Foundit and Glassdoor**: the extension has no access to these sites. Apply there
  yourself and confirm in JobPilot.
- **Multi-page wizards** beyond the first page: click **Fill** again on each page. The panel also tells you when new
  questions appear after you answer something.
- **Dates and month/year pickers** in education and employment sections: fill these yourself.

## When a form changes

Adapters rely on each platform's public form structure (ids, names, ARIA roles). If a platform changes its form,
fields are skipped with a reason rather than filled wrongly. To update an adapter, record the new form, add it to
`tests/fixtures/`, and adjust `src/content/adapters/<platform>.js`.
