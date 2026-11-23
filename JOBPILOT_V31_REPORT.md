# JobPilot V3.1: resume and Smart Apply corrections (engineering report)

Local only: nothing committed, pushed or deployed; no production data or containers touched (all runs used
throwaway SQLite backends in temp directories). Scoring docs: `docs/RESUME_AND_MATCH_SCORES.md`. Screenshots and
videos: `design-lab/preview/v31/`.

## 1. Root causes

| Screenshot issue | Root cause (verified how) |
|---|---|
| SmartRecruiters: "No application form is visible yet" with the form on screen | SmartRecruiters was handled by the **generic adapter**, which (a) reads only light DOM with `querySelectorAll`, so it can't see fields inside web components' **shadow roots**, and (b) only looked inside `<form>` elements once any visible `<form>` existed (e.g. a search box). SmartRecruiters builds its pages from `spl-*` web components with shadow roots (observed on the public listing page: `spl-job-location`, `spl-icon`, `spl-toaster`). The popup also printed that one message for *every* detection failure. Secondary: `www.smartr.me` (SmartRecruiters' alternate OneClick host) wasn't listed; the JobPilot → extension hand-off refused every non-Greenhouse/Lever/Ashby URL; clicks inside components were missed by the submit watcher (no `composedPath`). **Not verified on the live OneClick form**: it is behind a DataDome bot check for automated browsers; we did not bypass it. The shadow-DOM cause is consistent with the page structure observed on the listing page, and the fix handles it plus the non-`<form>` case. |
| Black squares in the PDF | Corruption starts at **source (A)**: Word resumes draw bullets with the Symbol/Wingdings fonts; their PDFs extract to Private Use Area code points (U+F0B7 …) or U+FFFD. The parser stored them in the profile, Studio copied them into the resume, and WeasyPrint printed glyphs no font has (blank `.notdef` boxes, or the black-diamond U+FFFD). Reproduced with the production image's font set (`fonts-liberation, lato, urw-base35, dejavu`): blank gaps and black diamonds; extraction (D) returned the PUA codes. The old checker only flagged emoji/PUA in the source and never looked at the PDF's glyphs. |
| "Bangalore, India" repeatedly reported as a missing job role | Two parser defects in `resume/profile_builder.py`: a **location line was taken as the role header** (on the date line: "Bangalore, India \| Jan 2022 – Present"; between title and dates; after the employer), so every role shared the same location as its "title"; and a long title with a comma was split into title/employer. The old read-back check then compared each Studio title against these mis-parsed titles **by title only**, so each entry produced its own "missing role" line naming the misread value. Also, studio PDFs emitted list markers as separate text lines at the end of the page, so a bullet without a full stop could be taken as the next role's header. |
| Checklist and PDF viewer disagree on pages | The preview served a **cached export keyed by content checksum without the renderer version**: after a renderer change it kept showing an old PDF, while the checker rendered fresh. The Check tab was cached per (version, job), **not per revision**, so after edits it could show an analysis of an older revision, and a slow answer could overwrite a newer one. |
| (found during the walkthrough) | The preview and the check exporting the same revision at once **raced**: same temp file name (`FileNotFoundError` on rename) and a duplicate cache row (`IntegrityError`) → HTTP 500. |

## 2. Files and functions changed

**Extension (2.3.0 → 2.4.0)**
- `src/content/adapters/smartrecruiters.js` (new): shadow-DOM adapter: detection by a visible e-mail field, labels from in-root `<label>`/host attributes, mapping by Angular `formcontrolname`/name tokens (first/last name, e-mail, **confirm e-mail**, phone, **dial code**, city, LinkedIn, website), cover-letter text field, resume drop-zone + read-back, cover-letter file detection, experience/education read from the form for review, `submitButton`, `submitErrors`, `confirmation`.
- `src/content/dom.js`: `deepAll` (bounded traversal incl. closed roots via `chrome.dom.openOrClosedShadowRoot`), `census` (diagnostics, counts only), `byId`, `closestDeep`, `orderCompare`; composed input/change events.
- `scan.js` (deep scan for `adapter.deep`, tree-scoped `aria-labelledby`, cross-tree order), `fill.js` (`email_confirm` alias, shadow-root listboxes), `fieldmap.js` (confirm-email label, unique dial-code matching: `+1` stays for the user), `submit.js` (composed clicks, deep errors), `core.js` (`detect` diagnostics), `adapters/generic.js` (no `<form>` assumption).
- `src/background.js`: `diagnose()` reasons (no form yet / fields unrecognised / closed components / form in another site's frame); hand-off allowed for known systems the user allowed; hand-off kept across the listing → form navigation; **never attaches a default resume**; records the attached file (`size`, `sha256`, where it was chosen).
- `src/lib/session.js` `resumeChoice`: popup pick → resume the user chose in JobPilot → none. `src/popup/popup.js`: diagnostics view; resume list starts at "Choose a resume…", says where the choice came from, Attach/Download disabled until chosen; manual-download fallback; cover-letter file note.
- `src/lib/config.js`: SmartRecruiters (+ smartr.me) as its own optional platform. `manifest.json`: 2.4.0. `PLATFORM_SUPPORT.md`.

**Backend**
- `core/textclean.py` (new): `clean` (invisible chars, odd spaces, ligatures, Symbol bullets), `unreadable`, `fold`.
- `resume/resume_parser.py`: `_clean_line`, `_join_lone_markers`. `resume/profile_builder.py`: `is_location`, location-aware `_header_block`, `_location_near`, `parse_experience` (location field, comma titles).
- `backend/services/resume_check.py` (new): `inspect_pdf` (pages, text, glyph trace), `character_findings`, `readback_findings`, `association_findings` (by dates, never by title), `issue` (stable ids), `dedupe`, `quality_score`, `alignment`, `RENDERER_VERSION`.
- `backend/services/studio_service.py`: `checksum` (+ renderer version), `export` (per-checksum lock + `IntegrityError` fallback), `_content_issues`, `feedback` (exact revision, 409 for stale, three scores), `suggestions` (categories A–E with why/effect/verified/actions), `_write_sections` (normalisation), `_doc_from_profile` (locations).
- `backend/services/studio_render.py`: normalised text; bullets drawn inline (extraction order). `storage.py`: unique temp names. `api/routes/studio.py`: `revision` param, `X-Revision`/`X-Checksum`, layout revision. `main.py`: exposed headers.
- `backend/services/apply_prep_service.py`: `_recommend_resume`, `_resume` (no silent default; recommendation with reason), readiness `resume_choice_needed`, exact revision/checksum recorded, `selected_by`/`checksum` to the extension.

**Frontend**
- `features/studio/Panels.tsx`: Check: three score cards with formulas, "why these differ", per-issue entry/field, Details (why/evidence/fix), **Go to**; revision line. Suggestions grouped A–E with why/effect/verified, Ignore / Go to / Accept, gaps never applicable.
- `features/studio/api.ts` (types; queries keyed by revision; `edit_field`), `StudioEditor.tsx` (`goTo`), `DocumentEditor.tsx` (`data-where`), `PreviewPane.tsx` (ignores older-revision PDFs).
- `features/apply/ResumeChooser.tsx` (recommendation, nothing preselected, "Not chosen yet", upload another file without changing the default), `Overview.tsx`, `types/api.ts`, extension 2.4.0 download links.

## 3. Preserved
Discovery, C search engine, match scoring (`scoring_v2` unchanged), Answer Memory and employer-specific answers, Apply Workspace, pairing, submission verification, interrupted-application recovery, Portal Connections, LinkedIn/Naukri guidance (blocked sites untouched), preferences, tracking, navigation, light/dark themes. Greenhouse/Lever/Ashby adapters unchanged; their offline e2e passes (39/39).

## 4. Tests and results
- Backend: full suite (excluding the two daemon-dependent e2e files): 576 tests, 573 passed, 3 skipped, 0 failed. New `tests/api/test_v31_resume_corrections.py` (17 tests): normalisation, parser bullets, Unicode export (no `.notdef` glyphs, text extractable), unreadable char → one issue at its field → accepted fix → +25, rejection changes nothing, 4 location layouts, identical locations/no duplicates, stable ids across reorder, multi-page page-count agreement (check = preview header = layout), stale revision 409, renderer-version cache key, three separate scores, no unevidenced skills, explicit resume selection end to end (package → extension), concurrent export race.
- Extension unit: 78/78 (11 new SmartRecruiters: root cause, dynamic form, unsupported closed components, autofill, ambiguous dial code, attach + verify, manual fallback, required validation, user submit + confirmation, site errors, other platforms unaffected).
- Frontend: 91/91; `tsc -b` clean; oxlint: no new findings (one pre-existing error in `clipper.bookmarklet.js`).

## 5. Browser verification
- `extension/e2e/run_sr_e2e.py`: real extension in Chromium on a **SIMULATED** SmartRecruiters page at the real address (request interception; site permission pre-granted in a temp copy of the manifest): 14/14 — listing → accurate "no form yet"; form detected; nothing preselected; attach verified by read-back; fill; gender/consent untouched; empty Experience reported; site validation; confirmation after the user's own click; no request sent.
- `extension/e2e/run_e2e.py` (Greenhouse/Lever/Ashby, offline copies, incl. one-click hand-off): 39/39.
- `design-lab/preview/v31_demo.py`: the real web app (Vite) + local backend with production fonts: Check, Details, Go to, Suggestions, accept → automatic re-check (56 → 81, Job Match unchanged), preview, Apply resume choice.

## 6. PDF export verification
Rendered with the production font set: no `.notdef` glyphs, ₹ ² “ ” → é present and extractable, bullets read in order ("• Built …"), multi-page counts agree. `pdf_before.png` / `pdf_after.png`: Symbol-font bullets rendered by the previous renderer (gaps) vs now (bullets).

## 7. Remaining limitations
- Live SmartRecruiters not verified (bot check for automated browsers); real field names may differ from the simulation. The adapter relies on meaning (labels, autocomplete, form-control names), but expect some "needs you" items on the live form. No authorised SmartRecruiters test posting was available.
- SmartRecruiters experience/education entries are read and reported, not created by JobPilot (SmartRecruiters fills them from the attached resume).
- Cover-letter *files* are not attached (JobPilot has a cover-letter text, not a file); the popup says so.
- On jobs not in JobPilot the review panel isn't updated after a confirmation page (nothing is tracked to record).
- Existing profiles keep titles parsed by the old parser until the user re-reads the resume or edits the entry; Studio shows those entries' problems (and characters) in Check.
- Read-back/association use JobPilot's own parser as a stand-in for applicant-tracking systems.
- Existing users must update the extension to 2.4.0 (frontend links updated; zip in `frontend/public/downloads/`).

## 8. Local preview
```
.venv/bin/python design-lab/preview/v31_demo.py          # web app walkthrough → design-lab/preview/v31/
.venv/bin/python extension/e2e/run_sr_e2e.py             # SmartRecruiters (simulated) in Chromium
.venv/bin/python extension/e2e/run_e2e.py                # Greenhouse / Lever / Ashby
.venv/bin/python -m pytest tests/api/test_v31_resume_corrections.py
(cd extension && npx vitest run); (cd frontend && npx vitest run)
```
