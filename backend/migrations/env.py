"""Alembic environment: schema for the JobPilot portal (PostgreSQL)."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import backend.models  # noqa: F401  (registers all tables on Base.metadata)
from backend.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL must be set to run migrations.")
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = Base.metadata


# Expression indexes created by raw SQL in migrations (not expressible in the models) are intentional.
SQL_ONLY_INDEXES = {"ix_jobs_fulltext"}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "index" and name in SQL_ONLY_INDEXES)


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
