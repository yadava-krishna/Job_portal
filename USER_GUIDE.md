# JobPilot: end-to-end guide

How to use JobPilot from sign-up to a tracked application, for the two kinds of people involved:

- **Job seekers (users):** everything happens in the web app and, optionally, the browser extension.
- **The portal owner (operator):** runs the server, adds users and keeps backups. JobPilot has **no admin login or
  admin screen yet** (planned as Phase 5). Owner tasks are done on the server machine with the commands in
  [Part B](#part-b-portal-owner-operator).

> **Credentials are not in this file.** The repository is public. The real values (the web address, the registration
> invite code, the owner's login e-mail) are kept on the server in `.deploy/CREDENTIALS.local.md`, which git ignores.
> Passwords are never written anywhere: JobPilot stores only a one-way hash, and nobody can read a password back.

| Credential | Who has it | Where it comes from |
|---|---|---|
| Web app address | everyone | `https://yadava-krishna.github.io/Job_portal/` |
| Registration invite code | owner, given to each new user | server `.env` → `REGISTRATION_INVITE_CODE` (copy in `.deploy/CREDENTIALS.local.md`) |
| User e-mail + password | each user | chosen by the user at registration (password: 10+ characters, upper- and lower-case letters and a number, not a common password) |
| Extension connection code | each user | created in Settings → Browser extension; works once, for 5 minutes |
| Server access (owner) | owner | the Ubuntu machine: `~/job_automation` (`.env` holds the database password, JWT secret and keys; never share or commit it) |

---

## Part A: Job seeker

### A1. Create your account and sign in

1. Open the web app address and choose **Create account**.
2. Enter your name, e-mail, a password, and the **invite code** the owner gave you.
3. Next time, use **Sign in** with your e-mail and password. Sessions renew automatically. **Sign out** is in
   Settings → Account & connection.

If the page says **JOB PORTAL OFFLINE**, the owner's server is not running or its address is being updated. Try again
in a few minutes.

### A2. Onboarding (first sign-in, about 5 minutes)

1. **Upload resume:** a PDF of up to 5 MB. It is stored privately for your account.
2. **Review profile:** JobPilot reads your resume. Correct anything wrong: name, contact details, roles with their
   dates (tick *current* for your present job), education and skills. Nothing is used until you confirm it.
3. **Job preferences:** titles, locations, work modes, employment types, experience, salary and minimum match score.
4. **Job portals:** choose which of LinkedIn, Indeed and Naukri you use (for clipping and alert e-mails).
5. **Confirm.** JobPilot creates a starter saved search from your preferences and runs it.

### A3. Complete your profile (Settings)

| Tab | What to do | Why it matters |
|---|---|---|
| **Resume & profile** | Add **LinkedIn, GitHub, portfolio and website** links. Keep role-specific **resume versions** and choose the **default** (used by the extension and new applications). Preview, download, rename or delete old versions | Forms ask for links and a resume |
| **Job preferences** | Titles, locations, work mode, salary, minimum score | Drives search and scoring |
| **Verified answers** | Salary (current is optional), expected salary, notice period, start date, work authorisation, visa sponsorship, relocation, shifts, relevant experience. Add **your own saved answers** to questions you are asked often | JobPilot never guesses these. Empty means "needs your input" |
| **Platforms** | Platform choices and the **Clip to JobPilot** bookmark | Saving jobs from LinkedIn, Indeed and Naukri |
| **Alert emails** | Optional: read your own job-alert e-mails (IMAP, app password, stored encrypted) | Finds jobs from LinkedIn, Indeed and Naukri alerts |
| **Notifications** | New-match alerts on or off, one alert per job or a daily summary, minimum score, sources | In-app bell (e-mail delivery is not available yet) |
| **Browser extension** | Create a connection code; see and disconnect connected browsers | Fill with JobPilot |
| **Account & connection** | Account details, sign out, backend status | |

### A4. Find jobs

- **Searches & sources:**
  - **Saved searches:** create searches (keywords, locations, remote, experience, industries, sources). Use
    **Run now**, or let them run daily or weekly. Each run shows which sources were checked and which failed.
  - **Companies:** add employers by pasting their **careers page** (JobPilot finds the Greenhouse, Lever, Ashby,
    SmartRecruiters or Recruitee board it uses and verifies it) or a board link. Workday and similar sites can't be
    searched automatically.
  - **Sources:** the health of every source, plus what is missing (for example Adzuna keys).
- **Discover jobs:** your feed, filtered by title or keyword, skill, company, location, work mode, experience, salary
  (when listed), employment type, posting date, source, match score and application status. Posting dates are
  labelled *Verified*, *Estimated* or *Unknown*. Unknown dates never count as recent.
- **Job details:** the full description, the score breakdown with reasons for and against (a score is a guide, not
  proof), and every site the job was seen on.
- **From LinkedIn, Indeed or Naukri:** open the job on that site in your own browser, click the **Clip to JobPilot**
  bookmark, then review and save. Or use **Add a job** (paste a link, the text, or a CSV/JSON file). JobPilot never logs
  into or scrapes these sites.
- **Save** jobs to look at later. **Dismiss** the ones you don't want.

### A5. Apply

1. On a job, click **Apply**. JobPilot prepares a package: a checklist, screening answers (from verified information
   only), the resume it will use and an optional cover letter.
2. Click **Open original listing**. For a Greenhouse job listed on the employer's own site, JobPilot may also offer
   **Open Greenhouse application form**, only when Greenhouse actually hosts the form for that job. Opening marks the
   application *Opened*, which is **not** *Applied*.
3. Fill the form on the employer's site, by hand or with the extension (A6). **You submit it yourself.**
4. Come back and choose **Yes, I submitted it** (add the reference ID if shown), **Not sure yet** or **I didn't
   apply**. Only *Yes* records it as applied, with the date and time.

### A6. Fill with JobPilot (browser extension, optional)

1. **Install:** see [extension/INSTALLATION.md](extension/INSTALLATION.md) (Chrome, Edge or Brave → Extensions →
   Developer mode → Load unpacked).
2. **Connect:** Settings → Browser extension → **Create connection code**. Type it into the extension within
   5 minutes. You never type your password into the extension.
3. On a **Greenhouse, Lever or Ashby** application form:
   1. Click the extension icon.
   2. **Attach my resume.** On Lever, do this first.
   3. Click **Fill with JobPilot**.
   4. Read the review panel on the page: *Filled*, *Please review*, *Needs your input*, *Kept your existing value*
      and *Skipped*, each with its reason.
   5. Complete the rest, solve any CAPTCHA, and **submit yourself**.
4. In the extension, click **I submitted it** (or **I didn't submit**). This is the same record as the web app's
   confirmation, and confirming twice changes nothing.
5. Demographic, consent, password and code fields are never filled. Disconnect any time in Settings.

### A7. Track applications

- **Applications** has three tabs:
  - **All applications:** with status filter.
  - **Pipeline board:** Applied → Screening → Assessment → Interview → Offer → Rejected, and *Archived*.
  - **Pending:** prepared or opened, not yet confirmed. **Continue** resumes the apply flow.
- Open an application to see how you applied, the reference ID, the history of every change, and to edit **notes**
  and a **follow-up date**. **Withdraw** or **Mark failed** when needed.
- **Dashboard** gives the overview. **Reports** has Excel exports (daily and full history).

### A8. Your data

Everything is private to your account: other users can't see your profile, resumes, jobs or applications. Delete old
resume versions in Settings. To close your account, ask the owner (B4). There is no self-service deletion yet.

---

## Part B: Portal owner (operator)

All commands run on the server in `~/job_automation`. **Never** run `docker compose down -v` and never delete the
`jobpilot_*` volumes.

### B1. Run the portal

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

### B2. Add users

1. Give the person the web address and the invite code (`grep REGISTRATION_INVITE_CODE .env`).
2. They register themselves (A1). You never set or see their password.
3. **Change the invite code** (for example after onboarding a group): edit `REGISTRATION_INVITE_CODE` in `.env`, then
   run `./deploy/start.sh`. Existing users are unaffected.

### B3. Reset a user's password (no self-service reset yet)

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

### B4. Deactivate or remove a user

- **Deactivate** (keeps their data; they can no longer sign in, and their extension stops working):
  `docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "update users set is_active=false where email=lower('"'"'user@example.com'"'"')"'`
- **Remove completely**, on the user's request: take a backup (B5) first. Then delete the user row (their profile,
  jobs, applications and credentials go with it) and their folder `/data/users/<id>` in the backend container.

### B5. Backups and restore

Follow [DEPLOYMENT.md §1](DEPLOYMENT.md) before every deployment, and from time to time. Restore steps are in §5.
Keep `backups/` and `.deploy/extension-key.pem` private: they contain personal data and the extension's signing key.

### B6. Optional set-up that needs you

| Item | Effect |
|---|---|
| ngrok static domain (free) in `.env` `NGROK_DOMAIN` | the public address never changes |
| Adzuna `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | adds Adzuna's job search to discovery |
| SMTP account | e-mail notifications (not built until then) |
| Decisions in [SOURCE_CAPABILITY_MATRIX.md](SOURCE_CAPABILITY_MATRIX.md) | Workable, remote-job aggregators, Jooble, Careerjet |
| Chrome Web Store developer account | publish the extension instead of the unpacked install |

---

## What JobPilot does not do

It does not submit applications for you or click Submit. It does not bypass CAPTCHA or OTP. It does not log into,
scrape or automate LinkedIn, Indeed or Naukri, and does not store your passwords for those sites. It does not mark
anything as applied until you confirm. It does not discover every job on the internet: only the sources listed in
[SOURCE_CAPABILITY_MATRIX.md](SOURCE_CAPABILITY_MATRIX.md).
