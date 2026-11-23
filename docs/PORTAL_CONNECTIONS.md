# Portal Connections: LinkedIn, Indeed, Naukri (V3.2, V3.3 UI)

What JobPilot does with each portal, how an owner turns on account linking, and the security checks behind it.

## What each portal gets

| Capability | LinkedIn | Indeed | Naukri |
|---|---|---|---|
| Official sign-in (`identity_auth`) | Sign In with LinkedIn using OpenID Connect, when configured | 3-legged OAuth, when configured | None exists for third-party apps |
| Account linked (`account_linked`) | After a completed sign-in | After a completed sign-in | Never (nothing to link) |
| Profile access (`profile_access`) | Account ID, name, photo, e-mail (scopes `openid profile email`) | E-mail (scope `email`) | None |
| Job retrieval (`job_retrieval`) | No: partner-only APIs | No: no published job-seeker API JobPilot is approved for | No |
| Application submission (`application_submission`) | No: Easy Apply has no API for JobPilot | No: Indeed Apply is for employers' systems | No |
| Native hand-off (`native_handoff`) | Yes | Yes | Yes |
| Reconnect required (`reconnect_required`) | Token expired (60 days, no refresh) or revoked | Refresh refused or revoked | n/a |

Each capability is reported separately by `GET /api/v1/portals`. There is no single "connected" flag. A linked
account never changes the JobPilot profile, never signs anyone in to JobPilot, and is not evidence of qualifications.
The V3 capabilities (`source`, `profile_guidance`, `application_handoff`, `assisted_submission`) are unchanged.

Jobs from these portals still reach JobPilot by pasted link, the clipper or alert e-mails. `backend/services/provider_jobs.py`
maps records from an *approved* job API into the normal ingest path with full provenance. `APPROVED_JOB_ACCESS` is empty,
so it refuses every portal.

## Card states (V3.3)

`GET /api/v1/portals` returns one row per portal, in card order LinkedIn, Naukri, Indeed, with `status`, `status_label`,
a one-line `summary`, one `reason` (the single thing in the way, said once), `limited`, `actions` and `capabilities`.

| `status` | Label | Primary action |
|---|---|---|
| `not_configured` | Not configured | Admin: **Set up {portal}**. Candidate: **Import {portal} job** (no Connect) |
| `not_linked` | Ready to connect | **Connect with {portal}** |
| `linked` | Connected / Connected with limited permissions | **Import {portal} job**; account under **Manage connection** |
| `reconnect_required` | Reconnect required | **Reconnect {portal}** |
| `authorization_required` | Provider authorization required | Admin: **Review setup**. No Connect: the admin's last real test was refused |
| `native_only` | Opens in browser (Naukri) | **Open Naukri** (new tab) |

Labels get " (simulated)" whenever the server or the linked identity uses `OAUTH_DEV_ENDPOINTS`. The page adds three
short-lived states: Connecting (on the way to the portal), Connection failed (the cause plus **Try again**), and
Temporarily unavailable (a check answered 502; the link is kept).

Capabilities are grouped in the **Capabilities & limitations** panel: Account (`identity_auth`, `account_linked`,
`profile_access`), Discovery (`listings`, `source`, `job_retrieval`), Applications (`application_handoff`,
`native_handoff`, `assisted_submission`, `application_submission`) and Profile improvement (`profile_guidance`).
`listings.count` is the number of feed jobs (new or shortlisted) from that portal, the same set Discover shows with
`?platform=`.

## Turning on linking (admin)

Connect buttons appear only when a portal has a client id, a secret and a valid redirect URI. Otherwise the card says
"Not configured": candidates get one plain reason, and admins get **Set up {portal}**.

**In the app (admins only).** Settings → Portal Connections → **Set up LinkedIn** / **Set up Indeed** opens a step-by-step
panel. Every call is `CurrentAdmin`-only (`/api/v1/admin/portals...`):
1. The developer console link (LinkedIn Developers; Indeed Partner Console docs), with the LinkedIn Company Page and
   Indeed partner-review requirements.
2. The product and scopes (`openid profile email`; Indeed `email offline_access`, never `employer_access`).
3. The callback URL as the server will send it (`<PUBLIC_APP_URL>/oauth-callback.html` or `*_REDIRECT_URI`), read-only
   with Copy. With no public address set, the panel says so and suggests the value; it never invents one.
4. Client ID and a masked Client Secret: `PUT /admin/portals/{p}/credentials`. The secret is encrypted with
   `CredentialCipher` in `portal_provider_configs` (migration 0018). It is write-only: no response, page or log
   contains it, and leaving it empty keeps the saved one. `DELETE` removes them. Environment variables take
   precedence; the panel then shows them read-only.
5. **Test connection**: `POST /admin/portals/{p}/test` starts the real sign-in with `purpose="test"`. It completes
   through the same callback and checks (state bound to the admin, `iss`, code exchange, ID token, userinfo), then
   links nothing and keeps no token. The result (`verified`, `authorization_required`, `cancelled`, `failed`) is
   stored and shown at the top of the panel. New credentials clear it. Credentials saved in the app never use
   `OAUTH_DEV_ENDPOINTS`, and a server running the simulator can't be "tested".

**By environment.** Alternatively:
1. **Redirect URL.** Register exactly `<PUBLIC_APP_URL>/oauth-callback.html` with the portal: HTTPS, no `#`, no query
   string. On GitHub Pages that is `https://<user>.github.io/Job_portal/oauth-callback.html`. To use a different URL, set
   `LINKEDIN_REDIRECT_URI` / `INDEED_REDIRECT_URI` to the exact value you registered.
2. **LinkedIn.** In the LinkedIn Developer Portal, create an app, add the product *Sign In with LinkedIn using OpenID
   Connect*, and add the redirect URL on the Auth tab. Then set `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET`.
   Two optional settings:
   - `LINKEDIN_PKCE=true`: only if LinkedIn has enabled PKCE for the app.
   - `LINKEDIN_REQUIRE_NONCE=true`: set it after a live sign-in shows LinkedIn returns the nonce. A nonce that is
     present is always checked.
3. **Indeed.** In the Indeed Partner Console, create an app with 3-legged OAuth. Creating these credentials starts a
   review by Indeed. Add the redirect URL to the allowlist, then set `INDEED_CLIENT_ID` and `INDEED_CLIENT_SECRET`.
   `INDEED_SCOPES` stays `email offline_access`; JobPilot refuses `employer_access` and any other scope.
4. Restart the backend. These variables are passed through `docker-compose.yml`; put the values in `.env` only.

## Connector hardening (V3.3)

**Dedicated key.** Saved client secrets use `security.ConnectorSecretCipher`, which accepts only `ENCRYPTION_KEY`, a
Fernet key. Unlike `CredentialCipher` it never derives a key from `JWT_SECRET` and never generates one.

Without a valid key:
- `PUT /admin/portals/{p}/credentials` answers 409 and stores nothing;
- the setup panel shows the reason and disables Save;
- environment-variable credentials and the rest of JobPilot keep working.

Each saved secret records the public id of its key (`client_secret_key_id`, migration 0019), so a missing or changed
key is reported by name.

**Readiness** (`readiness` on `/admin/portals` and `/portals`; `connection_service.start` enforces it):
| State | Blocks Connect | Set by |
|---|---|---|
| `missing_configuration` | yes | no credentials, or saved ones no key can open |
| `invalid_callback` | yes | no usable callback, or `redirect_uri_mismatch` in a test |
| `invalid_credentials` | yes | `invalid_client` in a test |
| `authorization_required` | yes | `unauthorized_client`, `invalid_scope` or `unsupported_response_type` in a test |
| `provider_unavailable` | no | portal 5xx, network error, or `temporarily_unavailable` in a test |
| `consent_declined` | no | the admin cancelled the test |
| `verified` | no | a real test passed for exactly this configuration |
| `unverified` | no | configured, not tested (or tested with other settings) |
| `simulated` | no | `OAUTH_DEV_ENDPOINTS`; always labelled |

Only an admin's test changes readiness. A candidate's sign-in result can't, because a browser can send any `error`.

A result applies only to the configuration fingerprint it was recorded for: source, client ID, callback and scopes.
New credentials clear it.

**Simulated vs real**
- Tests against the simulator are stored in `simulated_test` and never change the real result.
- An identity linked through the simulator shows "Reconnect required (simulated)" when the server uses the real
  portal. It never counts as linked, and its token is never sent to the real portal.
- `OAUTH_DEV_ENDPOINTS` is ignored in production.

**Recovery and rotation** (`backend/scripts/connector_secrets.py`; never prints a secret; dry run unless `--apply`):
1. **Inspect:** `docker compose exec backend python -m backend.scripts.connector_secrets status` shows, for each secret,
   which key opens it: `current`, `previous` or `legacy-jwt`.
2. **Rotate keys:**
   1. Set the new key as `ENCRYPTION_KEY` and the old one as `ENCRYPTION_KEY_PREVIOUS`, then restart. Sign-in keeps
      working, because the previous key is read-only.
   2. `rotate --from previous` (dry run), then `rotate --from previous --apply`.
   3. `status`, then remove `ENCRYPTION_KEY_PREVIOUS` and restart.
3. **Secrets saved before hardening without `ENCRYPTION_KEY`** (encrypted under the key derived from `JWT_SECRET`): set a
   new `ENCRYPTION_KEY`, keep the same `JWT_SECRET`, and run `rotate --from legacy-jwt --apply`.
4. **The original key is lost:** nothing can decrypt the secret. The tool leaves it untouched; an admin enters the
   secret again in Settings, which replaces it.

The tool re-encrypts a secret only after the old key opened it and the new ciphertext decrypts to the same value.

## Guided job import (V3.3)

`POST /api/v1/jobs/import/preview {url}` runs the same parsing as `/jobs/import` (`record_from_mapping`) and saves
nothing. It returns the recognised portal, the job ID, the normalised URL, and the existing feed entry if the job is
already there. JobPilot reads only the link and never downloads the portal's page. The guided dialog's steps:
1. Paste and check the link.
2. Add the title, company and description from the listing.
3. Review.
4. Save through `/jobs/import`.
5. **Prepare application** (Apply Workspace).

An unrecognised link can be entered by hand with a chosen portal; the unknown link itself is not saved.

## Flow and checks

1. **Start: `POST /portals/{p}/connect`.** JobPilot creates a pending sign-in for the signed-in user:
   - a 256-bit state, stored only as its SHA-256;
   - a nonce;
   - for Indeed, a PKCE S256 verifier, stored encrypted;
   - the exact redirect URI.

   The pending sign-in expires in 10 minutes, and only the newest per user and portal is kept. The browser goes to
   the portal in the same tab.
2. **Callback.** `oauth-callback.html` (`script-src 'self'`, `no-referrer`) keeps only `code`, `state`, `error`,
   `error_description` and `iss` in this tab's `sessionStorage`. It then `location.replace`s to a fixed Settings page,
   so nothing from the URL chooses where you go and the code isn't kept in history.
3. **Complete: `POST /portals/oauth/complete`.** The signed-in app sends the stored response. The backend rejects it,
   and records why in the audit log, when:
   - the state is unknown, already used or expired;
   - the state was started by another JobPilot user. This blocks the linking attack where someone gets their sign-in
     completed in your session, or yours in theirs.
   - for Indeed, the RFC 9207 `iss` is missing or wrong;
   - the portal reported an error or a cancellation.

   Otherwise it exchanges the code, sending the same redirect URI and the PKCE verifier. It then verifies the ID token:
   - signature with RS256 only, from the portal's JWKS (refetched once on an unknown key id);
   - issuer: LinkedIn `https://www.linkedin.com/oauth` (its discovery document) or `https://www.linkedin.com` (its
     guide); Indeed `https://secure.indeed.com`;
   - audience = client id, plus `azp` when there are several audiences;
   - `exp` and `iat`, with 60 s leeway;
   - the nonce.

   Last, it calls userinfo; its `sub` must match the ID token's. The account is linked by `(provider, subject)`, never
   by e-mail. That pair is unique, so one portal account can't be linked to two JobPilot users.
4. **Tokens.** Encrypted with `CredentialCipher` (Fernet; `ENCRYPTION_KEY`, else derived from `JWT_SECRET`). They are
   never returned to the browser and never written to logs: OAuth fields and JWTs are redacted in
   `core/logging_setup.py`. Audit entries carry no tokens, e-mail addresses or subject ids. The data export lists
   linked accounts without tokens, and deleting the account removes them (cascade).
5. **Check and refresh: `POST /portals/{p}/check`.**
   - Indeed: refreshes an expired access token and keeps the rotated refresh token.
   - LinkedIn: no refresh tokens (partner-only), so it asks for a reconnect after 60 days.
   - A 401, a refused refresh, or a different `sub` marks the link "Reconnect needed" and drops the access token.
6. **Disconnect: `DELETE /portals/{p}/connection`.** Deletes the identity and its tokens. Neither portal publishes a
   revocation endpoint, so the user is told where to remove JobPilot on the portal itself.

Endpoints are pinned in `backend/services/identity_providers.py` from the portals' discovery documents (checked
2026-11-23). `OAUTH_DEV_ENDPOINTS` replaces them with a local simulated provider for tests and demos; production
refuses it.

## Native hand-off (all three portals)

The Apply Workspace opens the original listing with `window.open` in the user's own browser. An existing session on the
portal is simply reused; JobPilot never touches passwords, OTPs or cookies.

- For portal jobs, **Open on {portal}** stays disabled until the user explicitly chooses a resume. The chosen revision
  and checksum are recorded.
- Opening the page is recorded as "employer page opened", never as applied.
- When the user says they applied, it's recorded as `user_reported` / `self_reported` ("not independently verified").

## Verification status

- **V3.3 admin setup and test:** covered by `tests/api/test_v33_portal_setup.py` (simulated providers) and
  `design-lab/preview/v33_demo.py`. The demo's test goes to the real LinkedIn authorization URL, but the browser
  intercepts it and replays a simulated refusal: the demo credentials are fake.
- **LinkedIn and Indeed:** not verified live. No developer credentials or partner approval are configured. Every test and
  the demo use simulated providers at the real URLs (`tests/api/test_v32_portal_accounts.py`) or on `127.0.0.1`
  (`design-lab/preview/v32_demo.py`).
- **Naukri:** the hand-off is exercised end to end in a browser against an intercepted, labelled stub page.
