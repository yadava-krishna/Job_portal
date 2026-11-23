"""Inspect, recover and rotate the encryption of saved LinkedIn/Indeed developer secrets (portal_provider_configs).

    python -m backend.scripts.connector_secrets status
    python -m backend.scripts.connector_secrets rotate --from previous     [--apply]
    python -m backend.scripts.connector_secrets rotate --from legacy-jwt   [--apply]

Run it where the backend runs (same DATABASE_URL, ENCRYPTION_KEY, JWT_SECRET), e.g.
    docker compose exec backend python -m backend.scripts.connector_secrets status

status   for each saved secret: which key opens it (current ENCRYPTION_KEY, ENCRYPTION_KEY_PREVIOUS, or the old key that
         was derived from JWT_SECRET before V3.3 hardening), and the key id it was saved with. Never prints a secret.
rotate   re-encrypts with the current ENCRYPTION_KEY the secrets that the chosen old key opens. A dry run unless --apply.
         A secret is rewritten only after the old key decrypted it and the new ciphertext was verified to decrypt to
         the same value. Secrets no key opens are left untouched: an admin re-enters them in Portal Connections.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from backend.config import get_settings
from backend.db import session_factory
from backend.models import PortalProviderConfig
from backend.security import ConnectorKeyError, ConnectorSecretCipher, connector_key_id, legacy_jwt_derived_key


def _opener(settings, which: str) -> ConnectorSecretCipher | None:
    key = settings.encryption_key_previous if which == "previous" else legacy_jwt_derived_key(settings)
    if not key:
        return None
    try:
        return ConnectorSecretCipher(settings, key=key)
    except ConnectorKeyError:
        return None


def status(settings) -> list[dict]:
    try:
        current = ConnectorSecretCipher(settings, key=settings.encryption_key or "")
    except ConnectorKeyError:
        current = None
    olds = {w: _opener(settings, w) for w in ("previous", "legacy-jwt")}
    out = []
    with session_factory()() as db:
        for row in db.execute(select(PortalProviderConfig).where(PortalProviderConfig.client_secret_encrypted.is_not(None))).scalars():
            opens = []
            if current and current._fernet_try(row.client_secret_encrypted):
                opens.append("current")
            opens += [w for w, c in olds.items() if c and c._fernet_try(row.client_secret_encrypted)]
            out.append({"provider": row.provider, "saved_with_key_id": row.client_secret_key_id,
                        "current_key_id": current.key_id if current else None, "opens_with": opens or ["none"]})
    return out


def rotate(settings, source: str, apply: bool) -> list[dict]:
    try:
        current = ConnectorSecretCipher(settings, key=settings.encryption_key or "")
    except ConnectorKeyError as exc:
        raise SystemExit(f"Refusing to rotate: {exc.message}") from None
    old = _opener(settings, source)
    if old is None:
        raise SystemExit("Refusing to rotate: " + ("ENCRYPTION_KEY_PREVIOUS isn't set or isn't a valid key." if source == "previous"
                                                   else "no JWT_SECRET to derive the old key from."))
    if old.key_id == current.key_id:
        raise SystemExit("Refusing to rotate: the old key and ENCRYPTION_KEY are the same.")
    report = []
    with session_factory()() as db:
        for row in db.execute(select(PortalProviderConfig).where(PortalProviderConfig.client_secret_encrypted.is_not(None))).scalars():
            if current._fernet_try(row.client_secret_encrypted):
                if row.client_secret_key_id != current.key_id and apply:
                    row.client_secret_key_id = current.key_id
                report.append({"provider": row.provider, "action": "already current"})
                continue
            plain = old._fernet_try(row.client_secret_encrypted)
            if plain is None:
                report.append({"provider": row.provider, "action": "left untouched: the old key doesn't open it (re-enter it in Portal Connections)"})
                continue
            new = current.encrypt(plain)
            if current._fernet_try(new) != plain:  # verify before overwriting anything
                report.append({"provider": row.provider, "action": "left untouched: verification of the new ciphertext failed"})
                continue
            if apply:
                row.client_secret_encrypted = new
                row.client_secret_key_id = current.key_id
            report.append({"provider": row.provider, "action": "re-encrypted" if apply else "would re-encrypt (dry run)"})
        if apply:
            db.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("rotate")
    r.add_argument("--from", dest="source", choices=("previous", "legacy-jwt"), required=True)
    r.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    settings = get_settings()
    rows = status(settings) if args.cmd == "status" else rotate(settings, args.source, args.apply)
    for row in rows:
        print("  ".join(f"{k}={v}" for k, v in row.items()))
    if not rows:
        print("No saved connector secrets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["status", "rotate", "connector_key_id"]
