# JobPilot Smart Apply (browser extension, v2.0)

A Chrome/Edge (Manifest V3) extension that fills job application forms from your JobPilot profile **when you click
Fill**. It then shows a **review of the form as it is actually filled**, and submits only when you **authorise that
one application**. JobPilot records the outcome only when it sees the employer's confirmation.

- Install: [INSTALLATION.md](INSTALLATION.md)
- Security and privacy: [SECURITY.md](SECURITY.md)
- What each platform supports: [PLATFORM_SUPPORT.md](PLATFORM_SUPPORT.md)

## Three modes

| Mode | Where | What happens |
|---|---|---|
| **A. Autofill and review** | All supported sites | JobPilot fills and checks the form. You submit on the page. JobPilot notices the submission and watches for the employer's confirmation. |
| **B. Assisted submission** | Greenhouse, Lever, Ashby | In the review panel you tick "I have reviewed this application", then click **Submit this application**. JobPilot re-reads the form, refuses if anything changed since your review, and otherwise clicks the site's own submit button **once**. |
| **C. Manual hand-off** | LinkedIn, Naukri, Indeed and unsupported pages | Nothing is injected. The popup shows your details to copy, downloads your resume, and links to JobPilot to record the application. |

## How it works

1. Open the employer's application form (from JobPilot's **Apply**). For Workday, iCIMS, SuccessFactors, Taleo,
   Zoho Recruit, Freshteam, Darwinbox, SmartRecruiters and other employer sites, the first time you use one, click
   **Allow Smart Apply on <site>**. Chrome asks you to confirm.
2. In the popup, choose the resume (an uploaded PDF, or a Resume Studio version as PDF or Word) and click **Attach**.
   The extension reads the file back from the form (name and size) and shows **Attached and checked** only if the
   form really holds it. If it doesn't, it says so and offers **Download**.
3. Click **Fill with JobPilot**. Fields are recognised by a deterministic classifier, with no AI. It combines the
   label, the HTML `autocomplete` token, the name/id, the placeholder and the input type into a confidence score:
   - **Confident fields** are filled.
   - **Uncertain or conflicting fields** are listed as *Not sure* and filled only if you click **Use JobPilot value**.
   - **Values worked out from your profile** (for example the city from "Bengaluru, Karnataka") are marked *Please
     review*.
   - **Salary, notice period, work authorisation, sponsorship, relocation and start date** come only from answers you
     confirmed. They are flagged so you tick each one before an assisted submission.
4. The **review panel** (docked at the side; you can collapse it or move it to the other side) shows:
   - the job;
   - your personal and professional details;
   - the documents attached;
   - every question, with its answer and where the answer came from (your profile, your saved answer, typed by you,
     or already on the form);
   - what is missing or invalid, and any upload errors.

   A fingerprint of the form is taken when you click **I have reviewed this application**. Any later change makes the
   review stale and must be reviewed again.
5. **Multi-step forms** (Workday): the panel shows the current step. When you move to the next step with the site's
   own button, it offers to fill that step.
6. **After submitting:**
   - With a confirmation signal (a thank-you page or message), the application becomes **Submitted (confirmed)**.
   - If the site shows errors, it goes back to **Needs information**.
   - Otherwise it is **Submission uncertain**, and JobPilot asks "Did it go through?". It asks again in the popup after
     a browser restart.
   - A submitted application can never be authorised again.

## Application states (recorded in JobPilot)

`draft → ready_to_fill → filling → needs_information / ready_for_review → reviewed → submission_authorized →
submission_pending → submitted_confirmed | submission_uncertain | failed`, plus `cancelled`. Clicking a button
never counts as submitted: `submitted_confirmed` requires a confirmation signal from the page, or your own answer.

## What it never does

- It never submits without your explicit authorisation for that application, and never on Workday or generic sites.
- It never touches CAPTCHA, OTP or password fields, and never creates accounts.
- It never answers gender, ethnicity, disability, veteran or other demographic questions, and never ticks consent
  boxes.
- It never runs on LinkedIn, Naukri or Indeed. Their terms forbid automation tools.
- It never reads cookies, history or saved passwords, and never sends profile data anywhere except the form you are
  filling.

## Layout

```
manifest.json            permissions, fixed extension ID (key)
src/background.js        service worker: device credential, JobPilot API calls, injection on click
src/lib/                 config (allowed hosts), api client, vault (IndexedDB)
src/popup/               popup UI
src/content/             dom.js, fieldmap.js (classifier), scan.js, fill.js, resume.js, review.js, submit.js, core.js,
                         panel.js (review panel), adapters/{greenhouse,lever,ashby,workday,generic}.js
tests/unit/              vitest (jsdom): vocabulary, fill rules, synthetic and locally recorded real forms
e2e/                     Playwright: real Chromium plus extension against a throwaway local backend (and --live forms)
scripts/package.mjs      builds dist/fill-with-jobpilot-<version>.zip
```

## Development

```bash
cd extension
npm install
npm test                 # unit tests
npm run package          # dist/fill-with-jobpilot-2.0.0.zip
# End to end (needs: pip install playwright httpx && playwright install chromium)
python e2e/run_e2e.py --project-python ../.venv/bin/python           # offline copies of the forms
python e2e/run_e2e.py --project-python ../.venv/bin/python --live    # also live public forms, fabricated data, never submitted
```

The extension has no runtime dependencies and no build step: what is in `src/` is what runs.
