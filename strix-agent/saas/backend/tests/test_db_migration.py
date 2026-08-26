from sqlalchemy import inspect, text

from app import models
from app.db import _add_missing_columns, engine


def test_add_missing_columns_backfills_a_column_added_to_an_existing_table() -> None:
    # Simulate a database that predates models.Pentest.extra_domain_id: drop
    # and recreate the pentests table without that column, the way a real
    # deployment's on-disk schema would look right after a code deploy adds
    # a new nullable column to an existing model.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS pentests"))
        conn.execute(
            text(
                "CREATE TABLE pentests ("
                "id VARCHAR PRIMARY KEY, org_id VARCHAR, target_type VARCHAR, "
                "target_id VARCHAR, target_label VARCHAR, scan_mode VARCHAR, "
                "status VARCHAR, schedule_id VARCHAR, started_at DATETIME, "
                "finished_at DATETIME, created_by VARCHAR, severity_counts JSON, "
                "created_at DATETIME, updated_at DATETIME"
                ")"
            )
        )

    columns_before = {c["name"] for c in inspect(engine).get_columns("pentests")}
    assert "extra_domain_id" not in columns_before

    _add_missing_columns()

    columns_after = {c["name"] for c in inspect(engine).get_columns("pentests")}
    assert "extra_domain_id" in columns_after

    # The backfilled column is actually usable, not just present in the schema.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pentests (id, org_id, target_type, target_id, extra_domain_id) "
                "VALUES ('p1', 'o1', 'repository', 'r1', 'd1')"
            )
        )
        row = conn.execute(text("SELECT extra_domain_id FROM pentests WHERE id = 'p1'")).one()
        assert row.extra_domain_id == "d1"


def test_add_missing_columns_is_a_noop_when_nothing_is_missing() -> None:
    from app.db import Base

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()  # must not raise on an already-current schema

    assert "extra_domain_id" in {c["name"] for c in inspect(engine).get_columns("pentests")}


def test_add_missing_columns_skips_tables_that_dont_exist_yet() -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS pentests"))

    _add_missing_columns()  # must not raise when a mapped table is simply absent

    from app.db import Base

    Base.metadata.create_all(bind=engine)  # restore for subsequent tests
    assert models  # keep the import used
