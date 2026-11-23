"""Official portal sign-in: LinkedIn (Sign In with LinkedIn using OpenID Connect) and Indeed (3-legged OAuth 2.0).

Endpoints are pinned, not discovered at run time, from each provider's published discovery document (checked
2026-11-23):
  LinkedIn  https://www.linkedin.com/oauth/.well-known/openid-configuration
            issuer https://www.linkedin.com/oauth (LinkedIn's OIDC guide prints https://www.linkedin.com; both are
            accepted, the signature from LinkedIn's JWKS is what proves the token). RS256. No PKCE, no revocation and no
            nonce claim advertised. Access tokens last 60 days; refresh tokens are for approved partners only.
  Indeed    https://secure.indeed.com/.well-known/openid-configuration
            issuer https://secure.indeed.com, RS256, PKCE S256, refresh tokens (offline_access), and the RFC 9207 `iss`
            parameter on the authorization response. No revocation endpoint. Access tokens last one hour.
Naukri publishes no sign-in for third-party apps, so it has no provider here: JobPilot hands off to naukri.com.

Signing in grants identity only. Neither provider gives JobPilot job search, saved jobs or application submission for a
job-seeker account; see portal_service for what is shown to users.

Every HTTP call goes through `_client()`; tests and local demos set TRANSPORT (or OAUTH_DEV_ENDPOINTS outside
production) to talk to a simulated provider instead.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
import jwt

from backend.config import BackendSettings

TRANSPORT: httpx.BaseTransport | None = None  # tests: httpx.MockTransport
LEEWAY_SECONDS = 60


class ProviderError(Exception):
    """kind: denied | invalid_grant | invalid_token | unauthorized | client | client_unauthorized | redirect |
    provider_error | network. client: the app's credentials were rejected (invalid_client); client_unauthorized: the
    app isn't approved for the product or scopes; redirect: the callback URL isn't registered."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    jwks_url: str
    issuers: tuple[str, ...]
    scopes: tuple[str, ...]
    oidc: bool              # an ID token is required (openid scope)
    pkce: bool
    require_nonce: bool
    iss_param: bool         # the authorization response must carry `iss` (RFC 9207)
    issues_refresh: bool
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    redirect_uri: str = ""
    problem: str | None = None  # why it can't be offered (not configured), else None
    simulated: bool = False  # OAUTH_DEV_ENDPOINTS: a local test server, not the real portal
    source: str = ""  # where the client credentials came from: env (server settings) | admin (saved in Portal Connections) | ""

    @property
    def configured(self) -> bool:
        return self.problem is None


# What each granted scope lets JobPilot read: shown as "Profile access" in Portal Connections.
SCOPE_FIELDS = {
    "linkedin": {"openid": ["Account ID"], "profile": ["Name", "Profile photo"], "email": ["E-mail address"]},
    "indeed": {"email": ["E-mail address"], "offline_access": []},
}
INDEED_ALLOWED_SCOPES = {"email", "offline_access"}
PROVIDERS = ("linkedin", "indeed")


def _redirect_problem(uri: str, settings: BackendSettings) -> str | None:
    try:
        parts = urlsplit(uri)
    except ValueError:
        return "The redirect URI isn't a valid URL."
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and local and settings.environment != "production"):
        return "The redirect URI must use HTTPS."
    if parts.fragment or "#" in uri or parts.query:
        return "The redirect URI must be exact: no # fragment and no query string."
    if not parts.hostname:
        return "The redirect URI must be an absolute URL."
    return None


def _redirect(settings: BackendSettings, explicit: str | None) -> str:
    if explicit:
        return explicit.strip()
    base = (settings.public_app_url or "").strip().rstrip("/")
    return f"{base}/oauth-callback.html" if base else ""


def credentials(settings: BackendSettings, key: str, db: Any = None) -> tuple[str, str, str, str | None]:
    """(client_id, client_secret, source, issue). Server environment settings win; otherwise what an admin saved in
    Portal Connections, decrypted here on the backend with the dedicated ENCRYPTION_KEY only (never a key derived from
    JWT_SECRET). `issue` says why saved credentials can't be used (no key, or a key that can't open them)."""
    env_id, env_secret = getattr(settings, f"{key}_client_id", None) or "", getattr(settings, f"{key}_client_secret", None) or ""
    if env_id or env_secret:
        return env_id, env_secret, "env", None
    if db is not None:
        from sqlalchemy import select

        from backend.models import PortalProviderConfig
        from backend.security import ConnectorKeyError, ConnectorSecretCipher

        row = db.execute(select(PortalProviderConfig).where(PortalProviderConfig.provider == key)).scalar_one_or_none()
        if row is not None and row.client_id and row.client_secret_encrypted:
            name = {"linkedin": "LinkedIn", "indeed": "Indeed"}.get(key, key)
            try:
                secret, _ = ConnectorSecretCipher(settings).decrypt(row.client_secret_encrypted)
            except ConnectorKeyError as exc:
                return row.client_id, "", "admin", f"The saved {name} secret can't be read: {exc.message}"
            if secret is None:
                return row.client_id, "", "admin", (
                    f"The saved {name} secret can't be decrypted with this server's ENCRYPTION_KEY"
                    + (f" (it was saved with key {row.client_secret_key_id})" if row.client_secret_key_id else "")
                    + ". Restore that key (or set it as ENCRYPTION_KEY_PREVIOUS), or enter the secret again.")
            return row.client_id, secret, "admin", None
    return "", "", "", None


def get(settings: BackendSettings, key: str, db: Any = None) -> Provider | None:
    """The provider as this server is set up. Pass `db` to include credentials an admin saved in Portal Connections."""
    if key not in PROVIDERS:
        return None
    client_id, client_secret, source, issue = credentials(settings, key, db)
    if key == "linkedin":
        p = Provider(
            key="linkedin", name="LinkedIn",
            authorize_url="https://www.linkedin.com/oauth/v2/authorization",
            token_url="https://www.linkedin.com/oauth/v2/accessToken",
            userinfo_url="https://api.linkedin.com/v2/userinfo",
            jwks_url="https://www.linkedin.com/oauth/openid/jwks",
            issuers=("https://www.linkedin.com/oauth", "https://www.linkedin.com"),
            scopes=("openid", "profile", "email"), oidc=True, pkce=settings.linkedin_pkce,
            require_nonce=settings.linkedin_require_nonce, iss_param=False, issues_refresh=False,
            client_id=client_id, client_secret=client_secret, source=source,
            redirect_uri=_redirect(settings, settings.linkedin_redirect_uri))
    elif key == "indeed":
        scopes = tuple(dict.fromkeys(s for s in (settings.indeed_scopes or "").replace(",", " ").split() if s))
        p = Provider(
            key="indeed", name="Indeed",
            authorize_url="https://secure.indeed.com/oauth/v2/authorize",
            token_url="https://apis.indeed.com/oauth/v2/tokens",
            userinfo_url="https://secure.indeed.com/v2/api/userinfo",
            jwks_url="https://secure.indeed.com/.well-known/keys",
            issuers=("https://secure.indeed.com",),
            scopes=scopes, oidc=False, pkce=True, require_nonce=False, iss_param=True, issues_refresh="offline_access" in scopes,
            client_id=client_id, client_secret=client_secret, source=source,
            redirect_uri=_redirect(settings, settings.indeed_redirect_uri))
    else:
        return None
    dev = (settings.oauth_dev_endpoints or {}).get(key)
    # The simulator never stands in for credentials an admin saved: those are for the real portal.
    if dev and settings.environment != "production" and source != "admin":
        p = _replace(p, authorize_url=dev["authorize"], token_url=dev["token"], userinfo_url=dev["userinfo"], jwks_url=dev["jwks"],
                     issuers=(dev["issuer"],), simulated=True)
    return _replace(p, problem=issue or _problem(p, settings))


def _replace(p: Provider, **kw: Any) -> Provider:
    from dataclasses import replace

    return replace(p, **kw)


def _problem(p: Provider, settings: BackendSettings) -> str | None:
    env = p.key.upper()
    if not p.client_id or not p.client_secret:
        return (f"Not set up on this JobPilot server: an admin needs to add {p.name} developer app credentials "
                f"(Set up {p.name} in Portal Connections, or {env}_CLIENT_ID and {env}_CLIENT_SECRET).")
    if not p.redirect_uri:
        return f"Not set up on this JobPilot server: set PUBLIC_APP_URL or {env}_REDIRECT_URI."
    bad = _redirect_problem(p.redirect_uri, settings)
    if bad:
        return f"Not set up correctly on this JobPilot server: {bad}"
    if p.key == "indeed":
        if "employer_access" in p.scopes:
            return "Not offered: employer access is for employer accounts, and JobPilot connects job-seeker accounts only."
        extra = set(p.scopes) - INDEED_ALLOWED_SCOPES
        if extra:
            return f"Not set up correctly: JobPilot asks Indeed only for email and offline_access, not {', '.join(sorted(extra))}."
        if not p.scopes:
            return "Not set up correctly: INDEED_SCOPES is empty."
    return None


# ---- PKCE, URLs ------------------------------------------------------------------------------------------------

def pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def authorization_url(p: Provider, state: str, *, nonce: str | None, verifier: str | None) -> str:
    q = {"response_type": "code", "client_id": p.client_id, "redirect_uri": p.redirect_uri, "state": state, "scope": " ".join(p.scopes)}
    if nonce:
        q["nonce"] = nonce
    if verifier:
        q.update(code_challenge=pkce_challenge(verifier), code_challenge_method="S256")
    return f"{p.authorize_url}?{urlencode(q)}"


# ---- HTTP -------------------------------------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(timeout=10.0, transport=TRANSPORT, follow_redirects=False, headers={"User-Agent": "JobPilot/1.0", "Accept": "application/json"})


def _json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        raise ProviderError("provider_error", "The provider sent a response JobPilot couldn't read.") from None
    if not isinstance(data, dict):
        raise ProviderError("provider_error", "The provider sent a response JobPilot couldn't read.")
    return data


def _token_request(p: Provider, form: dict[str, str]) -> dict[str, Any]:
    form = {**form, "client_id": p.client_id, "client_secret": p.client_secret}
    try:
        with _client() as c:
            resp = c.post(p.token_url, data=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except httpx.HTTPError:
        raise ProviderError("network", f"Couldn't reach {p.name}. Try again in a minute.") from None
    data = _json(resp) if resp.content else {}
    if resp.status_code != 200 or "access_token" not in data:
        err = str(data.get("error") or "")
        if err == "invalid_client":
            raise ProviderError("client", f"{p.name} rejected JobPilot's app credentials (invalid_client): check the client ID and secret.")
        if err in ("unauthorized_client", "invalid_scope"):
            raise ProviderError("client_unauthorized", f"{p.name} hasn't authorised JobPilot's app for this sign-in ({err}): "
                                                       f"check that {p.name} approved the product and scopes.")
        if err in ("invalid_redirect_uri", "redirect_uri_mismatch"):
            raise ProviderError("redirect", f"{p.name} didn't accept the callback URL ({err}): register exactly {p.redirect_uri}.")
        if resp.status_code >= 500:
            raise ProviderError("provider_error", f"{p.name} returned an error ({resp.status_code}). Try again later.")
        if err in ("invalid_grant", "invalid_request", "invalid_redirect_uri") or resp.status_code in (400, 401):
            raise ProviderError("invalid_grant", f"{p.name} didn't accept the sign-in (it may have expired). Start again.")
        raise ProviderError("provider_error", f"{p.name} returned an error ({resp.status_code}).")
    return data


def exchange_code(p: Provider, code: str, verifier: str | None) -> dict[str, Any]:
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": p.redirect_uri}
    if verifier:
        form["code_verifier"] = verifier
    return _token_request(p, form)


def refresh(p: Provider, refresh_token: str) -> dict[str, Any]:
    return _token_request(p, {"grant_type": "refresh_token", "refresh_token": refresh_token})


def userinfo(p: Provider, access_token: str) -> dict[str, Any]:
    try:
        with _client() as c:
            resp = c.get(p.userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError:
        raise ProviderError("network", f"Couldn't reach {p.name}. Try again in a minute.") from None
    if resp.status_code in (401, 403):
        raise ProviderError("unauthorized", f"{p.name} no longer accepts JobPilot's access. Reconnect to link it again.")
    if resp.status_code != 200:
        raise ProviderError("provider_error", f"{p.name} returned an error ({resp.status_code}).")
    data = _json(resp)
    if not isinstance(data.get("sub"), str) or not data["sub"]:
        raise ProviderError("provider_error", f"{p.name} didn't say which account this is.")
    return data


# ---- ID tokens --------------------------------------------------------------------------------------------------

_jwks: dict[str, tuple[float, dict[str, Any]]] = {}
_jwks_lock = threading.Lock()
JWKS_TTL = 3600


JWKS_MIN_REFETCH = 30  # seconds between forced refetches (unknown key id), so they can't be used to hammer the provider


def _keys(p: Provider, *, force: bool = False) -> dict[str, Any]:
    with _jwks_lock:
        hit = _jwks.get(p.jwks_url)
        age = time.monotonic() - hit[0] if hit else None
        if hit and (age < JWKS_MIN_REFETCH or (not force and age < JWKS_TTL)):
            return hit[1]
    try:
        with _client() as c:
            resp = c.get(p.jwks_url)
    except httpx.HTTPError:
        raise ProviderError("network", f"Couldn't fetch {p.name}'s signing keys.") from None
    if resp.status_code != 200:
        raise ProviderError("provider_error", f"Couldn't fetch {p.name}'s signing keys ({resp.status_code}).")
    data = _json(resp)
    with _jwks_lock:
        _jwks[p.jwks_url] = (time.monotonic(), data)
    return data


def clear_key_cache() -> None:
    with _jwks_lock:
        _jwks.clear()


def verify_id_token(p: Provider, token: str, nonce: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Signature (provider JWKS, RS256 only), issuer, audience, expiry, issued-at, nonce. Returns (claims, checks)."""
    bad = ProviderError("invalid_token", f"{p.name}'s sign-in token didn't pass JobPilot's checks. Nothing was linked.")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise bad from None
    if header.get("alg") != "RS256":
        raise bad
    kid = header.get("kid")

    def find(keys: dict[str, Any]):
        for k in keys.get("keys") or []:
            if (kid is None or k.get("kid") == kid) and k.get("kty") == "RSA" and k.get("use", "sig") == "sig":
                return k
        return None

    jwk = find(_keys(p)) or find(_keys(p, force=True))  # one refetch: the provider may have rotated keys
    if jwk is None:
        raise bad
    try:
        key = jwt.PyJWK(jwk, algorithm="RS256").key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=p.client_id, issuer=list(p.issuers), leeway=LEEWAY_SECONDS,
                            options={"require": ["iss", "sub", "aud", "exp", "iat"]})
    except jwt.ExpiredSignatureError:
        raise ProviderError("invalid_token", f"{p.name}'s sign-in token had expired. Start again.") from None
    except jwt.PyJWTError:
        raise bad from None
    if isinstance(claims.get("aud"), list) and len(claims["aud"]) > 1 and claims.get("azp") != p.client_id:
        raise bad
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise bad
    if "nonce" in claims:
        if not nonce or not hmac.compare_digest(str(claims["nonce"]), nonce):
            raise bad
        nonce_check = "matched"
    elif p.require_nonce:
        raise bad
    else:
        nonce_check = "not_returned"
    return claims, {"signature": "RS256", "issuer": claims["iss"], "audience": True, "expiry": True, "nonce": nonce_check}
