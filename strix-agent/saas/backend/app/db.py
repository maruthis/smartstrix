from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations() -> None:
    """Bring the schema to Alembic's ``head`` revision (``saas/backend/migrations/``).

    A database with no ``alembic_version`` row is either brand new (just
    created by ``create_all`` above — e.g. every test run) or predates this
    migration framework, back when schema drift was patched with an
    unversioned ``ALTER TABLE ... ADD COLUMN`` scan on every startup
    (``_add_missing_columns`` below). Either way, running that scan one
    more time guarantees the database's columns already match every
    current model field, so instead of replaying each migration's DDL
    against tables/columns that already exist (which would fail — e.g.
    "duplicate column"), the database is stamped at ``head`` directly.

    A database that already has an ``alembic_version`` row is on a normal
    footing and just needs ``upgrade head`` — this is the path every
    schema change should go through from now on: add a new Alembic
    revision (``uv run alembic revision --autogenerate -m "..."`` from
    ``saas/backend/``), not a new model field relied on to silently appear
    via the adoption bridge above.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    with engine.connect() as conn:
        current_revision = MigrationContext.configure(conn).get_current_revision()

    if current_revision is None:
        _add_missing_columns()
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


def _add_missing_columns() -> None:
    """Best-effort ``ALTER TABLE ... ADD COLUMN`` adoption bridge for a
    database that predates the Alembic migration framework — see
    ``_run_migrations`` above, which is the only caller. Not a substitute
    for writing migrations: this only ever runs once, against a database
    with no ``alembic_version`` row yet, and only ever adds columns, never
    drops or alters existing ones.
    """
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl_type = column.type.compile(dialect=engine.dialect)
                try:
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}"))
                except OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise
                existing.add(column.name)
