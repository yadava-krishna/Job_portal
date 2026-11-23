# Platform support

## Support levels (v2.0, 2026-11-16)

| Platform | Fill | Review panel | Assisted submit (Mode B) | Resume attach | How it was tested |
|---|---|---|---|---|---|
| Greenhouse, Lever, Ashby | Yes (site mappings plus classifier) | Yes | **Yes** | Yes, read back | Unit tests on synthetic and recorded forms; real-Chromium e2e including one authorised submission to a local copy (31/31) |
| Workday | Yes, one step at a time (data-automation-id mappings, button dropdowns) | Yes, shows the step | No: you submit on Workday | Yes, if the upload input is present | Unit tests on a **synthetic** Workday-style form only. **Not yet verified on a live Workday tenant** (they need a candidate account). |
| SmartRecruiters (jobs.smartrecruiters.com, www.smartr.me) | Yes: dedicated adapter that reads its web-component (shadow DOM) form by meaning (labels, autocomplete, form-control names), incl. confirm-email, dial code, city autocomplete, links, screening questions, message to the hiring team; after you allow the site | Yes; experience/education are listed from the form for review | No: you submit on the page; JobPilot records it only from SmartRecruiters' own confirmation | Yes, to the resume drop zone, read back | Unit tests on a **simulated** OneClick form (extension/tests/fixtures/synthetic/smartrecruiters.html) and a Chromium run of the real extension on it. The live OneClick form is behind a bot check for automated browsers, so it has **not** been verified on live SmartRecruiters. |
| iCIMS, SAP SuccessFactors, Oracle Taleo / Recruiting, Zoho Recruit, Freshteam, Darwinbox, other employer sites | Yes, from labels and HTML attributes only (generic adapter), after you allow the site | Yes | No | Yes, when a single resume/CV input is found | Unit tests on a synthetic generic form. **Not verified on live sites**: expect more *Not sure* and *Needs your input* items. |
| LinkedIn, Naukri, Indeed | **Never** | n/a | **Never** | n/a | Blocked in code (`BLOCKED` in `src/lib/config.js`), unit tested |

Terms checked on 2026-11-16:
- **LinkedIn:** its "Prohibited software and extensions" help page bans extensions that automate activity on the
  site.
- **Naukri:** its terms bar automated means. The Naukri Gulf terms name browser extensions explicitly.
- **Indeed:** its terms bar bots, and automating Indeed Apply is prohibited.

## Greenhouse, Lever and Ashby details (verified 2026-11-05 on live forms with fabricated data, never submitted)

Verified on 2026-11-05 against live public application forms, filled with **fabricated** test data and **never
submitted**: every write request to the platforms was blocked during the test, and none was a submission.

| | Greenhouse | Lever | Ashby |
|---|---|---|---|
| Pages | `job-boards.greenhouse.io/<board>/jobs/<id>`, `/embed/job_app?for=<board>&token=<id>`, also as an iframe on employer sites | `jobs.lever.co/<company>/<id>/apply` (+ EU) | `jobs.ashbyhq.com/<company>/<id>/application` (also embedded) |
| Name, e-mail, phone | first/last name by id; phone (country-format widget accepted) | full name, e-mail, phone | full name, e-mail, phone |
| Location | async location search: picked only when exactly one suggestion matches your location | text field (pick f## Limits

- **Dates and month/year pickers** in education and employment sections: fill these yourself.
- **Workday and generic sites:** account sign-in, phone-type and country-code dropdowns are left to you. Field names
  differ between employers, so some questions will need your input.
- **CAPTCHA, OTP and bot checks:** always yours. JobPilot keeps watching for the confirmation while you complete them.

 in the label block | `[data-field-path]` entries with titles |
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
