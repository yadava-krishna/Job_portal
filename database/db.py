"""SQLite access layer. All writes go through short transactions."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from core import timeutil
from core.models import ApplicationStatus, EligibilityResult, JobPosting, MatchResult, PipelineStatus
from database.models import JOB_JSON_LIST_FIELDS, SCHEMA, SCHEMA_VERSION

log = logging.getLogger(__name__)

ACTIVE_APPLICATION_STATUSES = (
    ApplicationStatus.AWAITING_APPROVAL,
    ApplicationStatus.APPROVED,
    ApplicationStatus.PENDING_MANUAL_SUBMISSION,
    ApplicationStatus.SUBMITTING,
    ApplicationStatus.NEEDS_VERIFICATION,
    ApplicationStatus.SUBMITTED,
)


class DuplicateApplicationError(Exception):
    pass


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 30000")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"Database {self.path} has schema v{version}, newer than this code (v{SCHEMA_VERSION}).")
        self.conn.executescript(SCHEMA)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    # ---- candidates ---------------------------------------------------------
    def upsert_candidate(self, name: str, profile: dict[str, Any]) -> int:
        now = timeutil.iso_now()
        stored = {k: v for k, v in profile.items() if k != "resume_text"}
        with self.tx() as c:
            c.execute(
                """INSERT INTO candidates (name, resume_path, resume_sha256, total_experience_months, profile_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET resume_path=excluded.resume_path, resume_sha256=excluded.resume_sha256,
                     total_experience_months=excluded.total_experience_months, profile_json=excluded.profile_json,
                     updated_at=excluded.updated_at""",
                (name, profile["resume"]["path"], profile["resume"]["sha256"], profile["total_experience"]["months"],
                 json.dumps(stored, ensure_ascii=False), now, now),
            )
        return self.one("SELECT id FROM candidates WHERE name = ?", (name,))["id"]

    def candidate_id(self, name: str) -> int | None:
        row = self.one("SELECT id FROM candidates WHERE name = ?", (name,))
        return row["id"] if row else None

    # ---- runs -----------------------------------------------------------------
    def start_run(self, trigger: str, attempt: int = 1) -> int:
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO daily_runs (run_date, trigger, status, attempt, pid, started_at) VALUES (?, ?, 'running', ?, ?, ?)",
                (timeutil.today().isoformat(), trigger, attempt, os.getpid(), timeutil.iso_now()),
            )
            return cur.lastrowid

    def finish_run(self, run_id: int, status: str, stats: dict | None = None, report_path: str | None = None, error: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE daily_runs SET status=?, finished_at=?, stats_json=?, report_path=?, error=? WHERE id=?",
                (status, timeutil.iso_now(), json.dumps(stats or {}), report_path, error, run_id),
            )

    def save_run_stats(self, run_id: int, stats: dict) -> None:
        with self.tx() as c:
            c.execute("UPDATE daily_runs SET stats_json=? WHERE id=?", (json.dumps(stats), run_id))

    def recover_stale_runs(self) -> list[int]:
        """Mark runs left 'running' by a dead process as interrupted."""
        stale = []
        for row in self.query("SELECT id, pid FROM daily_runs WHERE status = 'running'"):
            if row["pid"] == os.getpid() or not _pid_alive(row["pid"]):
                stale.append(row["id"])
        if stale:
            with self.tx() as c:
                c.executemany(
                    "UPDATE daily_runs SET status='interrupted', finished_at=?, error=COALESCE(error, 'Process ended before the run finished') WHERE id=?",
                    [(timeutil.iso_now(), rid) for rid in stale],
                )
        return stale

    def completed_run_exists(self, run_date: date, triggers: tuple[str, ...]) -> bool:
        marks = ",".join("?" * len(triggers))
        row = self.one(f"SELECT 1 FROM daily_runs WHERE run_date=? AND status='completed' AND trigger IN ({marks}) LIMIT 1", (run_date.isoformat(), *triggers))
        return row is not None

    def runs_on(self, run_date: date) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM daily_runs WHERE run_date = ? ORDER BY id", (run_date.isoformat(),))

    def recent_runs(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM daily_runs ORDER BY id DESC LIMIT ?", (limit,))

    # ---- jobs -----------------------------------------------------------------
    def get_job(self, job_key: str) -> sqlite3.Row | None:
        return self.one("SELECT * FROM jobs WHERE job_key = ?", (job_key,))

    def get_job_by_id(self, job_id: int) -> sqlite3.Row | None:
        return self.one("SELECT * FROM jobs WHERE id = ?", (job_id,))

    def insert_job(self, job: JobPosting, run_id: int | None) -> int:
        now = timeutil.iso_now()
        data = _job_columns(job)
        data.update(first_seen_at=now, first_seen_run_id=run_id, last_seen_at=now, last_seen_run_id=run_id, pipeline_status=PipelineStatus.DISCOVERED.value)
        cols = ",".join(data)
        with self.tx() as c:
            cur = c.execute(f"INSERT INTO jobs ({cols}) VALUES ({','.join('?' * len(data))})", tuple(data.values()))
            return cur.lastrowid

    def touch_job(self, job_id: int, run_id: int | None) -> None:
        with self.tx() as c:
            c.execute("UPDATE jobs SET last_seen_at=?, last_seen_run_id=?, seen_count=seen_count+1 WHERE id=?", (timeutil.iso_now(), run_id, job_id))

    def enrich_job(self, job_id: int, job: JobPosting) -> bool:
        """Fill fields that were empty (e.g. a description added later). Returns True if the description changed."""
        row = self.get_job_by_id(job_id)
        if row is None:
            return False
        new = _job_columns(job)
        updates = {k: v for k, v in new.items() if v not in (None, "", "[]") and (row[k] in (None, "", "[]")) and k != "job_key"}
        desc_changed = bool(job.description) and _hash(job.description) != row["description_hash"]
        if desc_changed:
            for k in ("description", "description_hash", *JOB_JSON_LIST_FIELDS):
                updates[k] = new[k]
            updates.update(match_score=None, match_category=None, match_json=None, pipeline_status=PipelineStatus.DISCOVERED.value)
        if updates:
            sets = ",".join(f"{k}=?" for k in updates)
            with self.tx() as c:
                c.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*updates.values(), job_id))
        return desc_changed

    def set_job_description(self, job_id: int, description: str, analysis_fields: dict[str, Any]) -> None:
        fields = {"description": description, "description_hash": _hash(description), **analysis_fields,
                  "match_score": None, "match_category": None, "match_json": None, "pipeline_status": PipelineStatus.DISCOVERED.value}
        fields = {k: (json.dumps(v) if isinstance(v, list) else v) for k, v in fields.items()}
        with self.tx() as c:
            c.execute(f"UPDATE jobs SET {','.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), job_id))

    def save_match(self, job_id: int, match: MatchResult, eligibility: EligibilityResult, status: PipelineStatus, run_id: int | None) -> None:
        with self.tx() as c:
            c.execute(
                """UPDATE jobs SET match_score=?, match_category=?, match_json=?, scoring_method=?, scored_at=?, scored_run_id=?,
                   eligibility_status=?, eligibility_json=?, pipeline_status=? WHERE id=?""",
                (match.overall_score, match.category, match.model_dump_json(), match.scoring_method, timeutil.iso_now(), run_id,
                 eligibility.status.value, eligibility.model_dump_json(), status.value, job_id),
            )

    def set_pipeline_status(self, job_id: int, status: PipelineStatus, note: str | None = None) -> None:
        with self.tx() as c:
            if note:
                c.execute("UPDATE jobs SET pipeline_status=?, notes=? WHERE id=?", (status.value, note, job_id))
            else:
                c.execute("UPDATE jobs SET pipeline_status=? WHERE id=?", (status.value, job_id))

    def jobs_needing_scoring(self) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM jobs WHERE match_score IS NULL AND pipeline_status IN ('DISCOVERED', 'SCORING_FAILED', 'NEEDS_DESCRIPTION') "
            "AND id NOT IN (SELECT job_id FROM applications) ORDER BY id"
        )

    def shortlist_without_application(self) -> list[sqlite3.Row]:
        return self.query(
            "SELECT * FROM jobs WHERE pipeline_status IN ('SHORTLISTED', 'LIMIT_DEFERRED') "
            "AND id NOT IN (SELECT job_id FROM applications) ORDER BY match_score DESC, id"
        )

    def find_jobs(self, ref: str) -> list[sqlite3.Row]:
        """Look up jobs by numeric id, exact job key, or URL."""
        if ref.isdigit():
            row = self.get_job_by_id(int(ref))
            return [row] if row else []
        return self.query("SELECT * FROM jobs WHERE job_key = ? OR url = ?", (ref, ref))

    # ---- applications ---------------------------------------------------------
    def create_application(self, job_id: int, candidate_id: int, status: ApplicationStatus, mode: str, run_id: int | None, **fields: Any) -> int:
        now = timeutil.iso_now()
        data = {"job_id": job_id, "candidate_id": candidate_id, "status": status.value, "mode": mode, "created_at": now,
                "created_run_id": run_id, "updated_at": now, **fields}
        try:
            with self.tx() as c:
                cur = c.execute(f"INSERT INTO applications ({','.join(data)}) VALUES ({','.join('?' * len(data))})", tuple(data.values()))
                app_id = cur.lastrowid
                c.execute("UPDATE jobs SET pipeline_status='APPLICATION_CREATED' WHERE id=?", (job_id,))
                c.execute(
                    "INSERT INTO application_events (application_id, job_id, run_id, event_type, to_status, details, created_at) VALUES (?, ?, ?, 'CREATED', ?, ?, ?)",
                    (app_id, job_id, run_id, status.value, f"mode={mode}", now),
                )
                return app_id
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc):
                raise DuplicateApplicationError(f"An application already exists for job {job_id}") from exc
            raise

    def get_application(self, app_id: int) -> sqlite3.Row | None:
        return self.one(
            "SELECT a.*, j.job_key, j.platform, j.company, j.title, j.url, j.match_score FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.id=?",
            (app_id,),
        )

    def get_application_by_job_key(self, job_key: str) -> sqlite3.Row | None:
        return self.one("SELECT a.* FROM applications a JOIN jobs j ON j.id=a.job_id WHERE j.job_key=?", (job_key,))

    def list_applications(self, statuses: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
        sql = "SELECT a.*, j.job_key, j.platform, j.company, j.title, j.url, j.match_score, j.match_category FROM applications a JOIN jobs j ON j.id=a.job_id"
        params: tuple = ()
        if statuses:
            sql += f" WHERE a.status IN ({','.join('?' * len(statuses))})"
            params = statuses
        return self.query(sql + " ORDER BY j.match_score DESC, a.id", params)

    def update_application(self, app_id: int, *, new_status: ApplicationStatus, expected_status: str, event_type: str,
                           details: str | None = None, run_id: int | None = None, **fields: Any) -> None:
        """Change status only if it is still `expected_status` (guards against concurrent changes)."""
        now = timeutil.iso_now()
        data = {"status": new_status.value, "updated_at": now, **fields}
        with self.tx() as c:
            row = c.execute("SELECT status, job_id FROM applications WHERE id=?", (app_id,)).fetchone()
            if row is None:
                raise KeyError(f"Application {app_id} not found")
            if row["status"] != expected_status:
                raise RuntimeError(f"Application {app_id} changed concurrently (now {row['status']}, expected {expected_status}).")
            c.execute(f"UPDATE applications SET {','.join(f'{k}=?' for k in data)} WHERE id=?", (*data.values(), app_id))
            c.execute(
                "INSERT INTO application_events (application_id, job_id, run_id, event_type, from_status, to_status, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (app_id, row["job_id"], run_id, event_type, expected_status, new_status.value, details, now),
            )

    def add_event(self, *, event_type: str, application_id: int | None = None, job_id: int | None = None, run_id: int | None = None, details: str | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO application_events (application_id, job_id, run_id, event_type, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (application_id, job_id, run_id, event_type, details, timeutil.iso_now()),
            )

    def events_for(self, app_id: int) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM application_events WHERE application_id=? ORDER BY id", (app_id,))

    def applications_created_on(self, day: date) -> int:
        return self.one("SELECT COUNT(*) FROM applications WHERE substr(created_at, 1, 10) = ?", (day.isoformat(),))[0]

    def active_application_for_fingerprint(self, fp: str, exclude_job_id: int) -> sqlite3.Row | None:
        if not fp:
            return None
        marks = ",".join("?" * len(ACTIVE_APPLICATION_STATUSES))
        return self.one(
            f"SELECT a.id, j.platform, j.job_key FROM applications a JOIN jobs j ON j.id=a.job_id "
            f"WHERE j.fingerprint=? AND j.id<>? AND a.status IN ({marks}) LIMIT 1",
            (fp, exclude_job_id, *[s.value for s in ACTIVE_APPLICATION_STATUSES]),
        )

    def recover_submitting_applications(self) -> list[int]:
        """An automated submission interrupted mid-way has unknown outcome: never retry it blindly."""
        ids = [r["id"] for r in self.query("SELECT id FROM applications WHERE status='SUBMITTING'")]
        for app_id in ids:
            self.update_application(app_id, new_status=ApplicationStatus.NEEDS_VERIFICATION, expected_status="SUBMITTING",
                                    event_type="RECOVERY", details="Interrupted during submission; outcome must be verified before any retry.")
        return ids

    # ---- platform status / errors ---------------------------------------------
    def add_platform_status(self, run_id: int, platform: str, status: str, access_mode: str, records_seen: int, jobs_found: int, error: str | None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO platform_status (run_id, platform, status, access_mode, records_seen, jobs_found, error, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, platform, status, access_mode, records_seen, jobs_found, error, timeutil.iso_now()),
            )

    def add_run_error(self, run_id: int | None, error_type: str, description: str, *, platform: str | None = None,
                      job_key: str | None = None, recovery_status: str = "NOT_RECOVERED") -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO run_errors (run_id, created_at, platform, job_key, error_type, description, recovery_status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, timeutil.iso_now(), platform, job_key, error_type, description[:2000], recovery_status),
            )

    # ---- reporting ------------------------------------------------------------
    def report_rows(self, day: date) -> list[sqlite3.Row]:
        """Jobs discovered on `day` plus jobs whose application changed on `day`."""
        d = day.isoformat()
        return self.query(
            """SELECT j.*, a.id AS app_id, a.status AS app_status, a.mode AS app_mode, a.created_at AS app_created_at,
                      a.submitted_at, a.reference_id, a.confirmation_text, a.confirmation_source, a.resume_path AS app_resume_path,
                      a.cover_letter, a.screening_json, a.error AS app_error, a.notes AS app_notes, a.approved_at
               FROM jobs j LEFT JOIN applications a ON a.job_id = j.id
               WHERE substr(j.first_seen_at, 1, 10) = :d
                  OR substr(j.last_seen_at, 1, 10) = :d
                  OR a.id IN (SELECT application_id FROM application_events WHERE substr(created_at, 1, 10) = :d)
               ORDER BY COALESCE(j.match_score, -1) DESC, j.id""",
            {"d": d},
        )

    def errors_on(self, day: date) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM run_errors WHERE substr(created_at, 1, 10) = ? ORDER BY id", (day.isoformat(),))

    def platform_status_on(self, day: date) -> list[sqlite3.Row]:
        return self.query(
            "SELECT p.* FROM platform_status p JOIN daily_runs r ON r.id=p.run_id WHERE r.run_date=? ORDER BY p.id", (day.isoformat(),)
        )

    def events_on(self, day: date) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM application_events WHERE substr(created_at, 1, 10) = ? ORDER BY id", (day.isoformat(),))


def _hash(text: str | None) -> str | None:
    return hashlib.sha256(text.encode()).hexdigest()[:32] if text else None


def _job_columns(job: JobPosting) -> dict[str, Any]:
    data = job.model_dump(exclude={"posted_date"})
    data["platform"] = job.platform.value
    data["posted_date"] = job.posted_date.isoformat() if job.posted_date else None
    data["description_hash"] = _hash(job.description)
    data["cover_letter_required"] = None if job.cover_letter_required is None else int(job.cover_letter_required)
    for f in JOB_JSON_LIST_FIELDS:
        data[f] = json.dumps(data[f], ensure_ascii=False)
    return data


def row_to_posting(row: sqlite3.Row) -> JobPosting:
    data = {k: row[k] for k in row.keys() if k in JobPosting.model_fields}
    for f in JOB_JSON_LIST_FIELDS:
        data[f] = json.loads(row[f] or "[]")
    data["posted_date"] = date.fromisoformat(row["posted_date"]) if row["posted_date"] else None
    data["cover_letter_required"] = None if row["cover_letter_required"] is None else bool(row["cover_letter_required"])
    data["company"] = data.get("company") or ""
    data["title"] = data.get("title") or ""
    data["fingerprint"] = data.get("fingerprint") or ""
    return JobPosting.model_validate(data)


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
