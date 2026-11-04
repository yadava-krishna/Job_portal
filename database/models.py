"""SQLite schema. Bump SCHEMA_VERSION and add a migration in db.py when changing it."""

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id                      INTEGER PRIMARY KEY,
    name                    TEXT NOT NULL UNIQUE,
    resume_path             TEXT NOT NULL,
    resume_sha256           TEXT NOT NULL,
    total_experience_months INTEGER,
    profile_json            TEXT NOT NULL,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_runs (
    id           INTEGER PRIMARY KEY,
    run_date     TEXT NOT NULL,
    trigger      TEXT NOT NULL CHECK (trigger IN ('manual', 'scheduled', 'catchup')),
    status       TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'interrupted')),
    attempt      INTEGER NOT NULL DEFAULT 1,
    pid          INTEGER,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    stats_json   TEXT,
    report_path  TEXT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON daily_runs(run_date, status);

CREATE TABLE IF NOT EXISTS jobs (
    id                       INTEGER PRIMARY KEY,
    job_key                  TEXT NOT NULL UNIQUE,      -- platform + job ID, or platform + hash
    platform                 TEXT NOT NULL,
    platform_job_id          TEXT,
    fingerprint              TEXT,                      -- normalised company|title across platforms
    company                  TEXT,
    title                    TEXT,
    url                      TEXT,
    location                 TEXT,
    work_mode                TEXT,
    employment_type          TEXT,
    experience_required      TEXT,
    exp_min_years            REAL,
    exp_max_years            REAL,
    salary_range             TEXT,
    salary_min_lpa           REAL,
    salary_max_lpa           REAL,
    posted_date              TEXT,
    description              TEXT,
    description_hash         TEXT,
    required_skills          TEXT NOT NULL DEFAULT '[]',
    preferred_skills         TEXT NOT NULL DEFAULT '[]',
    education_requirements   TEXT NOT NULL DEFAULT '[]',
    mandatory_qualifications TEXT NOT NULL DEFAULT '[]',
    application_method       TEXT,
    source                   TEXT,
    screening_questions      TEXT NOT NULL DEFAULT '[]',
    cover_letter_required    INTEGER,
    verification_flags       TEXT NOT NULL DEFAULT '[]',
    first_seen_at            TEXT NOT NULL,
    first_seen_run_id        INTEGER REFERENCES daily_runs(id),
    last_seen_at             TEXT NOT NULL,
    last_seen_run_id         INTEGER REFERENCES daily_runs(id),
    seen_count               INTEGER NOT NULL DEFAULT 1,
    pipeline_status          TEXT NOT NULL DEFAULT 'DISCOVERED',
    match_score              REAL,
    match_category           TEXT,
    match_json               TEXT,
    scoring_method           TEXT,
    scored_at                TEXT,
    scored_run_id            INTEGER REFERENCES daily_runs(id),
    eligibility_status       TEXT,
    eligibility_json         TEXT,
    notes                    TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(pipeline_status);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen_at);

CREATE TABLE IF NOT EXISTS applications (
    id                  INTEGER PRIMARY KEY,
    job_id              INTEGER NOT NULL REFERENCES jobs(id),
    candidate_id        INTEGER NOT NULL REFERENCES candidates(id),
    status              TEXT NOT NULL,
    mode                TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    created_run_id      INTEGER REFERENCES daily_runs(id),
    updated_at          TEXT NOT NULL,
    approved_at         TEXT,
    submitted_at        TEXT,
    reference_id        TEXT,
    confirmation_text   TEXT,
    confirmation_source TEXT,
    resume_path         TEXT,
    resume_sha256       TEXT,
    cover_letter        TEXT,
    screening_json      TEXT NOT NULL DEFAULT '[]',
    package_path        TEXT,
    error               TEXT,
    notes               TEXT,
    UNIQUE (candidate_id, job_id)                      -- one application per job, ever
);
CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status);

CREATE TABLE IF NOT EXISTS application_events (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER REFERENCES applications(id),
    job_id         INTEGER REFERENCES jobs(id),
    run_id         INTEGER REFERENCES daily_runs(id),
    event_type     TEXT NOT NULL,
    from_status    TEXT,
    to_status      TEXT,
    details        TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_app ON application_events(application_id);
CREATE INDEX IF NOT EXISTS idx_events_created ON application_events(created_at);

CREATE TABLE IF NOT EXISTS platform_status (
    id            INTEGER PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES daily_runs(id),
    platform      TEXT NOT NULL,
    status        TEXT NOT NULL,           -- ok | partial | error | disabled
    access_mode   TEXT NOT NULL,           -- assisted | automated
    records_seen  INTEGER NOT NULL DEFAULT 0,
    jobs_found    INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    checked_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_errors (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER REFERENCES daily_runs(id),
    created_at      TEXT NOT NULL,
    platform        TEXT,
    job_key         TEXT,
    error_type      TEXT NOT NULL,
    description     TEXT NOT NULL,
    recovery_status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_errors_created ON run_errors(created_at);
"""

# Columns of `jobs` that are JSON-encoded lists.
JOB_JSON_LIST_FIELDS = (
    "required_skills",
    "preferred_skills",
    "education_requirements",
    "mandatory_qualifications",
    "screening_questions",
    "verification_flags",
)
