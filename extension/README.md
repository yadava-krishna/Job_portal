# Fill with JobPilot (browser extension)

A Chrome/Edge (Manifest V3) extension that fills **Greenhouse, Lever and Ashby** application forms from your JobPilot
profile **when you click Fill**. You review every field and **submit the form yourself**. Then you tell JobPilot
whether you applied, and that is recorded in your application history.

- Install: [INSTALLATION.md](INSTALLATION.md)
- Security and privacy: [SECURITY.md](SECURITY.md)
- What each platform supports: [PLATFORM_SUPPORT.md](PLATFORM_SUPPORT.md)

## How it works

1. In JobPilot, open a job and click **Apply**, then **Open original listing** (or, for Greenhouse jobs listed on an
   employer's own site, **Open Greenhouse application form** when JobPilot has verified that Greenhouse hosts it).
   JobPilot records the application as *Opened*, which is not *Applied*.
2. Click the extension's toolbar icon. It detects the platform and shows whether the job is in your JobPilot jobs.
3. **Attach my resume** (Lever: do this first) attaches your default JobPilot resume to the form's resume field.
   **Download** saves it so you can attach it yourself.
4. **Fill with JobPilot** fills the fields it can identify with confidence:
   - **From your profile:** name, e-mail, phone, location, current company and title, links, and most recent
     education.
   - **Your verified answers:** salary, notice period, sponsorship, relocation and your saved answers. These are
     matched to option lists only when exactly one option fits.
   - **Suggested answers** (for example years of experience calculated from your dates) are filled but marked
     *Please review*.
5. A review panel on the page lists what was filled, what to review, what needs your input (with links to fix your
   profile), what was kept because the field already had a value, and what was skipped, with the reason for each.
6. You check everything, complete the rest, solve any CAPTCHA and press Submit on the employer's form.
7. Back in the extension, click **I submitted it** (optionally with the reference ID) or **I didn't submit**. The
   same confirmation exists in JobPilot (Applications, Continue). Confirming twice changes nothing.

## What it never does

It never submits, clicks Submit or Apply, or touches CAPTCHA, OTP or password fields. It never answers gender,
ethnicity, disability, veteran or other demographic questions, and never ticks consent boxes. It never reads cookies,
history or saved passwords, and never runs on LinkedIn, Indeed, Naukri or any site other than the three platforms
above. It never sends profile data anywhere except the form you are filling.

## Layout

```
manifest.json            permissions, fixed extension ID (key)
src/background.js        service worker: device credential, JobPilot API calls, injection on click
src/lib/                 config (allowed hosts), api client, vault (IndexedDB)
src/popup/               popup UI
src/content/             fieldmap.js, core.js (fill engine), panel.js, adapters/{greenhouse,lever,ashby}.js
tests/unit/              vitest (jsdom): vocabulary, fill rules, synthetic and locally recorded real forms
e2e/                     Playwright: real Chromium plus extension against a throwaway local backend (and --live forms)
scripts/package.mjs      builds dist/fill-with-jobpilot-<version>.zip
```

## Development

```bash
cd extension
npm install
npm test                 # unit tests
npm run package          # dist/fill-with-jobpilot-1.0.0.zip
# End to end (needs: pip install playwright httpx && playwright install chromium)
python e2e/run_e2e.py --project-python ../.venv/bin/python           # offline copies of the forms
python e2e/run_e2e.py --project-python ../.venv/bin/python --live    # also live public forms, fabricated data, never submitted
```

The extension has no runtime dependencies and no build step: what is in `src/` is what runs.
