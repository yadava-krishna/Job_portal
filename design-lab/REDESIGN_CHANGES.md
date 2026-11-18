# JobPilot frontend redesign: what changed

Branch `redesign/paper-jade` (pushed as its own branch; not merged to main and not deployed). Frontend only: no backend, database,
extension or deployment change. All 65 tests pass; typecheck and production build are clean.

## 1. Look and feel
- **Colours.** Green/teal identity replaced by cobalt (#365CF5, main actions, links, active nav), indigo (#29236E,
  headings), violet on lavender (selection, secondary emphasis), coral on peach (small highlights: counts, "top pick",
  "to learn"). Green (#1F7A50) now appears only for confirmed outcomes; amber for "needs you"; red for failures. Full
  dark theme with the same identity. Every text colour checked at ≥ 4.5:1 in both themes (three suggested values were
  darkened for that).
- **One colour language everywhere.** Old hard-coded Tailwind colours (emerald, amber, sky, rose…) are remapped onto
  these roles, so older screens match without rewriting each one. Status badges and source badges use tokens; job
  sources are neutral (Greenhouse no longer looks like "success").
- **Type.** Manrope (headings), Geist (body), Geist Mono (scores, counts, dates). All OFL and self-hosted.
- **Shapes.** Pill buttons with a press effect, 16–22px rounded panels, soft shadows only on things you can click.
- **Illustration.** An original dusk-sky "flight path" scene (night sky in dark mode) on Home and sign-in.
- **Voice.** Gen Z touches where people actually notice them: page titles ("Hey, Asha. We're so back.", "Fresh roles,
  just dropped", "Glow-up season", "The receipts", "Your setup, your rules", "Small steps, big W's", "Passport era?"),
  success toasts ("Saved. Locked in.", "Offer details saved. Big W 🎉", "Rejection recorded. Their loss, honestly.",
  "Platforms saved. Say less.") and empty states ("Nothing here rn", "Discovery is cooking 🍳"). Field labels,
  errors, privacy, eligibility and status wording stay plain so nothing important is lost in slang.

## 2. Navigation
- 12 flat menu items → 4 areas (Home, Jobs, Applications, Career) + footer (Settings, My mentees, Admin by role).
  Every old link still works.
- **Collapsible sidebar** (240 ↔ 72px, button or `[` key, remembered). Collapsed shows icons with tooltips. A highlight
  slides to the active page. Live counts: new matches (Jobs), things needing you (Applications). Phone: drawer.
- **⌘K / Ctrl+K** jumps to any page or settings section.
- **One calm loading screen** instead of three messages in a row; it only explains itself when something is slow.
- Saved theme now applies from the first paint on every screen (sign-in, onboarding, loading).

## 3. Discover (Jobs → Matches)
- One compact toolbar: Jobs/Internships, search, location, work mode, date, saved searches, Filters (with a count).
  Sources and date chips moved inside Filters. Discovery status is one line under the title.
- **Square job tiles (default)**: company and source, save, title, a match meter (score, label, skills matched),
  location, experience, salary, posting date with Verified/Estimated, eligibility and visa flags, top skills + "learn X",
  View full JD, Apply, ⋯ (dismiss, original listing, other locations). **Grid/List switch** (remembered) keeps the
  compact rows too.
- **Pagination**: the backend returns 20 jobs per request and the old page never asked for more, so jobs past the
  first 20 were never shown. Now 24 per page with Previous/Next, page numbers and "Showing 25–48 of 312";
  changing search or filters goes back to page 1.
- Sort moved next to the result count; keyboard shortcuts (j/k/o/s/a/d) unchanged.

## 4. Full job description
- One pop-up used everywhere: fixed header (company, title, place, pay, match score), section jumps (Overview,
  Responsibilities, Requirements, Preferred, Match & eligibility, Full description; only sections with real data),
  the description scrolls inside it (never cut short), fixed action bar (Open original listing, Tailor a resume,
  Prepare for interview, Save, Apply). Escape closes it and returns focus to the button you used. Full screen on phones.

## 5. Home
- Slim greeting band, then above the fold: five fresh matches, "Needs your attention", "Coming up"; one row of
  Submitted / Saved / Resume / Discovery; numbers as one strip; charts in an expandable "Trends" section.

## 6. Applications, Apply, Reports
- Stage-count strip that filters; List / Board / Pending; board with pinned column headers, lifted-card drag feedback,
  keyboard move menu kept; detail pop-up with a "where it stands" timeline including Smart Apply steps.
- Apply dialog shows a four-step route (package → employer form → fill & review → confirmed), green only when
  confirmed, and says plainly nothing is sent without your click.
- Reports: one question per block with a big number and a simple chart.

## 7. Settings
- Ten cramped tabs → a two-column workspace: left menu in five groups (My profile, Job discovery, Smart Apply,
  Notifications, Privacy & account), one section at a time with a status chip and one save button per form. All
  `?tab=` links still work.
- **Profile welcome** at the top of "Resume & profile": your initials, "Hey, <name>. This is you on paper.", headline,
  location, resume, confirmed status, top skills, a profile-strength ring with the next one or two things to add,
  quick stats (experience, skills, projects, education) and "Edit details" (jumps to the form).

## 8. Other pages
- Resume Studio: editor and live preview side by side, each scrolling on its own; Check/Suggestions/History counts;
  template selection feedback; export shows progress then "Downloaded".
- Searches & companies, Onboarding (stepper + "your profile so far", now dark-mode aware), Career, Interview prep,
  Mentor, My mentees, International, Admin (toasts instead of browser pop-ups), offline screen: compact layouts on the
  same tokens.

## 8b. Resume templates in plain words
- Template names and descriptions no longer use recruiting jargon. "Classic ATS" → **Clean & Simple**, "Modern
  Professional" → **Modern**, "Technical Engineer" → **Tech & Data**, "Experienced Professional" → **Experienced**.
- Badges: "ATS-safe" → **Safe for online forms**; "For reading by people" → **Best for email & print**. Hovering
  either explains what it means. Font names say what they look like ("Times-style (classic)").
- The New resume dialog explains itself in plain words. (Frontend wording only; the server's template ids are unchanged.)

## 8c. Unsaved changes in Settings
- Edit a Settings section and try to leave (another section, a sidebar link, ⌘K, refresh or closing the tab): a
  dialog asks **Save changes / Discard / Keep editing**. An "Unsaved changes" badge shows while edits are pending.

## 9. Motion (visible, and off when the system asks for reduced motion)
- Page change: content rises 12px and fades in (320ms). Tile cascades play on first view and on a new page of
  results, not again when you come back.
- Job tiles, list rows and Home panels rise in one after another (45ms apart); match meters fill from zero;
  the profile-strength ring draws in.
- Sidebar width animates (260ms); the active highlight slides; pop-ups scale up from 94% and lift (320ms);
  tabs and Settings sections slide in (300–340ms); buttons press to 97%; tiles lift on hover; save icon pops.
- Measured in the running app (not assumed): sidebar 240→136→86→72px; pop-up opacity 0→0.31→0.75→1; tiles
  0.74/0.59/0.33… as they cascade; with reduced motion everything is instant.
- Video: `design-lab/preview/videos/jobpilot-redesign-walkthrough.mp4` (and .gif).

## 10. Still open
- Smart Apply still can't see the employer tab; status follows what the extension reports; you submit in its panel.
- Extension install still needs Developer mode until it is on the Chrome Web Store.
- Satoshi font not used until its licence is checked for self-hosting.
