# JobPilot: Security Review (Phase 0, 2026-11-04; updated Phase 1, 2026-11-04)

Scope: backend API, data storage, deployment (Docker, ngrok, GitHub Pages), frontend, browser clipper.
Findings marked **verified** were reproduced against the running system; the others are from code inspection.
No secrets are reproduced in this document.

## Summary

| # | Severity | Finding | Status |
|---|---|---|---|
| S1 | **High** | Database password and registration invite code were printed in a chat transcript | **Fixed (Phase 1)**: password and invite rotated, verified |
| S2 | **High** | Auth rate limiting is bypassable with a forged `X-Forwarded-For` header (**verified**: 12/12 attempts unthrottled with spoofed header vs 429 after 10 without) | **Fixed (Phase 1)**: verified live and by regression tests |
| S3 | Medium | OpenAPI docs and schema publicly reachable through the tunnel (**verified** 200 on `/api/v1/docs`, `/openapi.json`) | **Fixed (Phase 1)**: verified live and by tests |
| S4 | Medium | Single shared invite code, no expiry or usage limit, no revocation per invitee | Replace with invites table (Phase 1/5) |
| S5 | Medium | No role model: no admin separation, no audit log | Phase 1 + 5 |
| S6 | Medium | Refresh token in `localStorage`: readable by any XSS on the Pages origin | Mitigate with CSP + no-HTML rendering; keep rotation and reuse detection |
| S7 | Medium | No Content-Security-Policy on the GitHub Pages frontend | Add `<meta http-equiv="Content-Security-Policy">` (Phase 6) |
| S8 | Low | No password reset or account deletion / data export (privacy rights) | Phase 4/7 |
| S9 | Low | Health endpoint discloses version and scheduler timing publicly | Reduce public detail (Phase 8) |
| S10 | Low | In-flight discovery runs lost on restart; stuck `running` rows | **Mitigated (Phase 2)**: runs left running >30 min are marked failed "interrupted by restart" at startup; a durable queue is still Phase 8 |
| S13 | Medium | Phase 2 adds outbound HTTP to job-board APIs from the server, partly driven by user input (board URLs/tokens) | **Controlled**: see details |
| S11 | Low | No automated database backup | Phase 8 (`pg_dump` timer + restore doc) |
| S14 | Medium | Phase 3: browser-extension credentials and a server fetch of user-supplied careers-page URLs | **Controlled**: see details |
| S12 | Info | PDF parsing runs in the API process (PyMuPDF on untrusted files) | Size/page limits exist; consider a subprocess with timeout (Phase 8) |

## Details and remediation

**S1: Exposed credentials. FIXED (Phase 1).** The Postgres password and the invite code were shown in a conversation. Postgres is not reachable from outside Docker, which limited the impact, but both were treated as compromised.
*Done (no data loss, new values never printed):*
1. A backup was taken and verified first (`pg_dump -Fc` + storage tarball + SHA-256 sums). It was restored into a throwaway Postgres 16 with identical row counts. The backup stays local in `backups/`, which is gitignored.
2. The role password was changed in the database with `ALTER ROLE jobpilot WITH PASSWORD …`, sent over stdin. Updating `POSTGRES_PASSWORD` alone does not change an existing role. `.env` was then synchronised and only postgres and backend were recreated; the volume is untouched.
3. Verification ran over the Docker network from the backend container. The in-container loopback uses `trust` auth, so a local test proves nothing. Result: old password **rejected**, new password **accepted**; backend health shows the database connected; the existing user and their resume and profile rows are intact.
4. `REGISTRATION_INVITE_CODE` was rotated. The old code returns 403 on registration and the new one is accepted. No probe accounts were created.
5. Not rotated: `JWT_SECRET` (would sign everyone out) and the ngrok authtoken (never displayed). Both are optional.

**S2: Rate-limit bypass. FIXED (Phase 1).** There were three layers to the cause:
(a) `client_ip` used the *first* `X-Forwarded-For` entry, which the client controls.
(b) uvicorn ran with `--forwarded-allow-ips='*'`, which does the same.
(c) Found during live verification: **ngrok forwards the client's own `X-Forwarded-For` as a separate header line and appends its own line after it**, so `headers.get()` returned only the forged line.

*Fix:*
- uvicorn now runs with `--no-proxy-headers`.
- `resolve_client_ip()` honours `X-Forwarded-For` only when the direct peer is in `TRUSTED_PROXY_CIDRS` (default loopback + 172.16.0.0/12, the Docker networks). It joins **all** header lines and walks the chain right to left, returning the first untrusted address. A malformed hop falls back to the peer.
- Per-account throttling: after `LOGIN_FAILURES_PER_ACCOUNT` (10) failures within `LOGIN_FAILURE_WINDOW_MINUTES` (15), that email gets 429 from any address, including with the correct password, until the window passes. A successful login clears the counter.

*Evidence:*
- 8 integration tests in `tests/api/test_security.py`: untrusted peer with spoofed header; forged left entries behind the proxy; ngrok-style split header lines; separate buckets per real client; per-account lock across rotating addresses; case-insensitive lock key; reset on success; plus 13 resolver unit cases.
- With the old header handling patched back in, the split-line tests fail. They pass with the fix.
- Live through the tunnel: 13 logins with rotating forged `X-Forwarded-For` and a different email each time (so the account lock cannot mask the result) returned 401×10 then 429×3. Before the fix this was 12/12 unthrottled.

**S3: Public API docs. FIXED (Phase 1).** `DOCS_MODE` is `public` / `local` / `off`. The default is `local` when `ENVIRONMENT=production` (the Docker image) and `public` in development. `local` serves `/api/v1/docs` and `/api/v1/openapi.json` only when the *resolved* client address is in `TRUSTED_PROXY_CIDRS`, which means this machine or its containers. ReDoc and the framework default `/docs`, `/redoc` and `/openapi.json` are disabled. The root endpoint advertises docs only to callers allowed to see them.
*Evidence:*
- Live through the tunnel: `/api/v1/docs` and `/openapi.json` return 404, including with forged `X-Forwarded-For: 127.0.0.1` or `172.20.0.1`. On `127.0.0.1:8000` they return 200; ReDoc returns 404.
- 6 tests cover production public/tunnel/forged/local, `off` and development modes, and rejection of an invalid `DOCS_MODE`.
- Note: the local web UI on `:3080` is published on the LAN. With Docker's default port publishing, nginx sees the LAN client's real address (untrusted), so docs stay hidden there too. If the userland proxy were in use, LAN clients would appear as the Docker gateway and could see the docs. That is acceptable for a home LAN and would be removed by setting `FRONTEND_BIND=127.0.0.1`.

**S4: Invites.** Table `invites(token_hash, email?, role, max_uses, used_count, expires_at, created_by, revoked_at)`; admin UI to create, copy, revoke; registration consumes atomically.

**S5: RBAC and audit.** `users.role ∈ {user, admin}` enforced by a backend dependency (`require_admin`); every admin read of user-level data and every admin action written to `audit_logs(actor_id, action, target_type, target_id, ip, at, details)`. Admin views of resumes and personal data require an explicit "view personal data" action that is itself audited. Frontend hiding is cosmetic only.

**S6/S7: Token storage and XSS.** Keep bearer tokens (cross-site cookies between github.io and ngrok are unreliable), but: strict CSP (`default-src 'self'; connect-src 'self' https://*.ngrok-free.app https://*.ngrok.app; img-src 'self' data: https:; script-src 'self'`), never render job-description HTML (we render text only; keep it that way), short access-token TTL (15 min, already), refresh rotation with reuse detection (already).

**S14: Browser extension and careers-page fetch (Phase 3, implemented 2026-11-05).**

*Extension credentials:*
- **Pairing code:** 8 characters, single use, 5 minutes, hashed, ≤ 3 live, rate-limited. It is exchanged for a `jpx_` device credential (256-bit, hashed at rest) with scopes `autofill:read` and `applications:track`.
- **Lifetime:** 90 days, rotated monthly with a 2-minute grace period, revocable from Settings or the extension. Every request is checked; revoked credentials are refused immediately.
- **Separation:** device credentials are accepted only on `/extension/*`, and user JWTs are not accepted there.
- **What the extension can read:** the minimal autofill profile, classified answers, and the resume (on click, no-store, rate-limited, audited).
- **Storage:** the credential lives in the extension's IndexedDB, out of content scripts' reach.
- **Permissions:** activeTab, scripting, storage and the three ATS hosts only.
- **Behaviour on employer pages:** never submits (`safeClick` allows only choice inputs, listbox options and `type=button` buttons); never fills sensitive, consent, password, OTP or CAPTCHA fields.

*Careers-page fetch:*
- **Request-forgery protection:** https on port 443 only; no IP literals or credentials; every resolved address must be global; the connection is pinned to the vetted IP with TLS verified against the hostname; each redirect is re-checked (≤ 3).
- **Limits:** 2 MB and 10 s per page, 20 checks per hour per user. Only that one page is read. Bot-protected pages are reported, never evaded.

Details: extension/SECURITY.md, SOURCE_CAPABILITY_MATRIX.md, tests in tests/api/test_extension.py and test_discovery_expansion.py.

**S13: Outbound job-board requests (Phase 2).**
- User input never becomes a URL. A board link is parsed to one of three fixed API hosts (Greenhouse, Lever with an EU variant, Ashby), and the token must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$` (no `/`, `..` or spaces). Anything else is rejected before any request is made, so there is no SSRF to internal addresses.
- Requests carry an identifying User-Agent and no cookies or credentials.
- Limits: 25-second timeout, 25 MB body cap, JSON only. Not-found boards are cached for 6 hours to avoid hammering.
- Job descriptions are converted to plain text on the server (scripts and styles dropped) and are never rendered as HTML.
- Users cannot read each other's saved searches, runs, watchlists, notifications or feed items (tests return 404, never 403). Job rows are public listings shared between users; all per-user state lives in `user_jobs`.
- Tests: `test_bad_tokens_rejected_before_any_request`, `test_parse_board_url_rejects_other_sites`, `test_response_size_cap`, `test_saved_searches_watchlists_and_notifications_are_private`, `test_two_users_get_independent_matches_from_shared_boards`. In the test suite, any request not explicitly mocked fails, so no test can reach a real board by accident.

## Controls already in place (verified in code/tests)
Argon2id hashing with rehash-on-login · uniform timing on unknown emails · password policy · 15-min HS256 access JWT · rotating refresh tokens stored as SHA-256, family revocation on reuse · every user-data query scoped by `user_id`, cross-user access returns 404 (tested for each resource) · resume uploads: size, `%PDF` magic, PyMuPDF open, encryption and page checks, server-generated filenames, ownership plus path check on download · Fernet-encrypted IMAP passwords · CORS allowlist · security headers · Postgres on an internal-only network, backend bound to 127.0.0.1 · secrets in `.env` (600, gitignored) · log redaction of emails, phones, keys and passwords · history scanned clean of secrets and personal data before the repo went public.
