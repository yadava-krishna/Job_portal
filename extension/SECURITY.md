# Fill with JobPilot: security and privacy

## Permissions

| Permission | Why |
|---|---|
| `activeTab` | Act on the tab you opened the popup on, only after you click |
| `scripting` | Insert the fill scripts into that tab's application form, only after a click |
| `storage` | Declared for extension pages. The credential itself is kept in the extension's IndexedDB (below) |
| Hosts: `job-boards.greenhouse.io`, `boards.greenhouse.io` (+ EU), `jobs.lever.co` (+ EU), `jobs.ashbyhq.com` | Fill those forms, including when an employer embeds a Greenhouse or Ashby form in an iframe on its own site |

**Not requested:** `<all_urls>`, `cookies`, `tabs`, `history`, `webRequest`, `downloads`, `identity`, `externally_connectable`.
There are no content scripts that run automatically and no background activity. Nothing runs on any page until you
click. The JobPilot server is reached through CORS (the server allow-lists this extension's fixed origin), so no host
permission for the server or for `*.ngrok-free.app` is needed.

## Connecting (pairing) and the credential

- **Pairing code:** created by the logged-in user in JobPilot Settings. 8 characters (about 40 bits), valid for 5
  minutes, single use, at most 3 outstanding per user, stored only as a hash.
- **Rate limits:** pairing attempts are limited to 10 per 10 minutes per address.
- **Exchange:** the extension exchanges the code for a device credential `jpx_…` (256 bits). It is returned once and
  the server stores only its SHA-256 hash.
- **Scopes:** `autofill:read` and `applications:track`. The credential is accepted **only** on `/api/v1/extension/*`,
  never on the rest of the API, and the user's login tokens are not accepted there.
- **Lifetime:** 90 days, rotated by the extension monthly. The old credential keeps working for a 2-minute grace
  period so a lost response cannot lock the device out.
- **Revocation:** *Disconnect* in JobPilot Settings or in the extension revokes it immediately. The server checks
  every request (hash lookup, not revoked, not expired, user active, scope).
- **Audit:** pair, rotate, revoke and resume-download events are written to the audit log, without any secrets.
- **Where it is kept:** the extension's own IndexedDB (origin `chrome-extension://…`), used only by the service
  worker. Content scripts run in employer pages and cannot open that database. The credential is never put into a
  page, a URL, a DOM attribute or `chrome.storage`. The end-to-end test checks that the page's HTML, globals and
  storage contain nothing from the extension.

## What the extension receives from JobPilot

- **Profile (minimal):** name, e-mail, phone, location, current company and title, links, most recent education,
  and verified answers. Never your summary, skills, other jobs, scores or anyone else's data.
- **Answers:** for the form's question labels, only from your verified information (classified Verified, Suggested
  or Needs input). The labels are not stored.
- **Resume:** downloaded only when you click Attach or Download, with `Cache-Control: no-store`, rate-limited and
  audited. The bytes are kept in memory only long enough to build the file for the form's upload field. There is no
  resume URL that works without the credential.

Profile data in the popup and service worker is held only for the duration of one action. Nothing is logged to the
console and no analytics are collected.

## What the extension does on employer pages

- It reads the form's fields and labels to decide what to fill. Question labels go to JobPilot to look up your
  verified answers, and nowhere else.
- It writes values only into visible, enabled fields. A value already present is kept unless you choose overwrite,
  and a value you typed after filling is never replaced.
- It never fills sensitive (demographic or EEO), consent, password, OTP or CAPTCHA fields. It never clicks Submit or
  any button that could submit, never calls `submit()` or `requestSubmit()`, and never dispatches submit events.
  These rules are enforced in code (`safeClick`) and tested.
- The review panel lives in a closed Shadow DOM. Its buttons react only to genuine user clicks (`event.isTrusted`).
- The service worker accepts messages only from the extension's own popup page. Content scripts and web pages cannot
  ask it for anything, and external messages are refused.

## Residual risks

- **The employer's page sees what is filled.** Once you click Fill, the values are in the employer's form, as if you
  had typed them. A page's own scripts (including analytics) can read them before you submit.
- **Local device access:** someone with control of your browser profile could use the credential until you revoke
  it. Its scopes limit what can be done: read the minimal profile and resume, and record applications.
- **Programmatic resume attachment** depends on the page accepting a file set by script. When it doesn't, you attach
  the file yourself.
