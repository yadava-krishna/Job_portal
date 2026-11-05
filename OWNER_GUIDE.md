# JobPilot: owner guide (server tasks)

For the person who runs the JobPilot server. Job seekers should read USER_GUIDE.md instead. Real access details are in the git-ignored `.deploy/CREDENTIALS.local.md` on the server; JobPilot has no admin login yet.


All commands run on the server in `~/job_automation`. **Never** run `docker compose down -v` and never delete the
`jobpilot_*` volumes.

## 1. Run the portal

| Task | Command |
|---|---|
| Start, or redeploy after code changes | `./deploy/start.sh` (prints the local UI, the public backend URL and the invite code) |
| Publish a new web app build | `./deploy/deploy_frontend.sh` |
| Stop (data kept) | `./deploy/stop.sh` |
| Status | `docker ps --format '{{.Names}} {{.Status}}'` (four `jobpilot-*` containers, all healthy) |
| Health | `curl -s "$(cat .deploy/last_published_url)/api/v1/health" -H 'ngrok-skip-browser-warning: 1'` |
| Logs | `docker compose logs -f backend` |
| Local UI / API docs (this machine only) | `http://localhost:3080`, `http://127.0.0.1:8000/api/v1/docs` |

After a crash or reboot the containers come back by themselves. To keep the public address stable, set the free ngrok
static domain or add the cron entry: see [DEPLOYMENT.md §3](DEPLOYMENT.md).

## 2. Add users

1. Give the person the web address and the invite code (`grep REGISTRATION_INVITE_CODE .env`).
2. They register themselves (see USER_GUIDE.md). You never set or see their password.
3. **Change the invite code** (for example after onboarding a group): edit `REGISTRATION_INVITE_CODE` in `.env`, then
   run `./deploy/start.sh`. Existing users are unaffected.

## 3. Reset a user's password (no self-service reset yet)

```bash
docker compose exec backend python - <<'PY'
import getpass
from sqlalchemy import update
from backend.config import get_settings
from backend.db import init_engine, session_factory
from backend.models import RefreshToken, User
from backend.security import hash_password, password_problems
init_engine(get_settings().database_url)
email = input("User e-mail: ").strip().lower()
pw = getpass.getpass("New password (not shown): ")
assert not password_problems(pw, email), password_problems(pw, email)
with session_factory()() as db:
    u = db.query(User).filter(User.email == email).one()
    u.password_hash = hash_password(pw)
    db.execute(update(RefreshToken).where(RefreshToken.user_id == u.id).values(revoked_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)))
    db.commit()
    print("Password changed; existing sessions signed out.")
PY
```
Give the new password to the user through a private channel and ask them to change it. (Changing your own password
in the app is not available yet; this command is the way for now.)

## 4. Deactivate or remove a user

- **Deactivate** (keeps their data; they can no longer sign in, and their extension stops working):
  `docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "update users set is_active=false where email=lower('"'"'user@example.com'"'"')"'`
- **Remove completely**, on the user's request: take a backup (section 5) first. Then delete the user row (their profile,
  jobs, applications and credentials go with it) and their folder `/data/users/<id>` in the backend container.

## 5. Backups and restore

Follow [DEPLOYMENT.md §1](DEPLOYMENT.md) before every deployment, and from time to time. Restore steps are in §5.
Keep `backups/` and `.deploy/extension-key.pem` private: they contain personal data and the extension's signing key.

## 6. Optional set-up that needs you

| Item | Effect |
|---|---|
| ngrok static domain (free) in `.env` `NGROK_DOMAIN` | the public address never changes |
| Adzuna `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | adds Adzuna's job search to discovery |
| SMTP account | e-mail notifications (not built until then) |
| Decisions in [SOURCE_CAPABILITY_MATRIX.md](SOURCE_CAPABILITY_MATRIX.md) | Workable, remote-job aggregators, Jooble, Careerjet |
| Chrome Web Store developer account | publish the extension instead of the unpacked install |
