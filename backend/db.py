"""SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # SQLite enforces foreign keys only when asked
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10, pool_timeout=5,
                         connect_args={"connect_timeout": 3})


def init_engine(url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    _engine = make_engine(url or get_settings().database_url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    return _engine or init_engine()


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    return _SessionLocal  # type: ignore[return-value]


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def check_database() -> tuple[bool, str | None]:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # report, never raise, from health checks
        return False, type(exc).__name__
