"""Deletion respects ownership and erases durable data after process restarts."""

from contextlib import nullcontext

import psycopg
import pytest

from backend.shared import billing_store, session_store
from backend.shared.config import get_settings

OWNER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def deletion_db(monkeypatch):
    # Every relation is connection-local. Never mutate persistent test/dev data.
    with psycopg.connect(get_settings().DATABASE_URL) as conn:
        conn.execute("SET search_path TO pg_temp")
        conn.execute("CREATE TEMP TABLE users (id uuid PRIMARY KEY)")
        conn.execute("CREATE TEMP TABLE sessions (id text PRIMARY KEY, user_id uuid, status text DEFAULT 'completed')")
        conn.execute("CREATE TEMP TABLE resume_files (session_id text, owner_user_id text)")
        conn.execute("CREATE TEMP TABLE wallet_transactions (user_id uuid)")
        conn.execute("INSERT INTO users VALUES (%s), (%s)", (OWNER, OTHER))
        conn.execute("INSERT INTO sessions (id, user_id) VALUES ('owned', %s), ('other', %s)", (OWNER, OTHER))
        conn.execute("INSERT INTO resume_files VALUES ('owned', %s), ('other', %s), ('upload', %s)", (OWNER, OTHER, OWNER))
        conn.commit()
        monkeypatch.setattr(session_store, "_connect", lambda: nullcontext(conn))
        monkeypatch.setattr(billing_store, "_connect", lambda: nullcontext(conn))
        yield conn


@pytest.mark.requires_postgres
def test_session_deletion_never_removes_another_owners_resume(deletion_db):
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        deletion_db.execute(f"CREATE TEMP TABLE {table} (thread_id text)")
    deletion_db.commit()
    assert session_store.delete_session("other", OWNER) is False
    assert deletion_db.execute("SELECT session_id FROM resume_files WHERE session_id = 'other'").fetchone()


@pytest.mark.requires_postgres
def test_session_deletion_succeeds_without_optional_checkpoint_tables(deletion_db):
    assert session_store.delete_session("owned", OWNER) is True
    assert deletion_db.execute("SELECT id FROM sessions WHERE id = 'owned'").fetchone() is None
    assert deletion_db.execute("SELECT session_id FROM resume_files WHERE session_id = 'owned'").fetchone() is None


@pytest.mark.requires_postgres
def test_session_deletion_removes_artifacts_and_checkpoints(deletion_db):
    for table, column in (("failure_screenshots", "session_id"), ("skyvern_task_artifacts", "session_id"),
                          ("session_outcomes", "session_id"), ("checkpoints", "thread_id")):
        deletion_db.execute(f"CREATE TEMP TABLE {table} ({column} text)")
        deletion_db.execute(f"INSERT INTO {table} VALUES ('owned'), ('other')")
    deletion_db.commit()
    assert session_store.delete_session("owned", OWNER)
    for table, column in (("failure_screenshots", "session_id"), ("skyvern_task_artifacts", "session_id"),
                          ("session_outcomes", "session_id"), ("checkpoints", "thread_id")):
        assert deletion_db.execute(f"SELECT {column} FROM {table}").fetchall() == [("other",)]


@pytest.mark.requires_postgres
def test_account_deletion_erases_durable_sessions_uploads_and_credentials(deletion_db):
    for table in ("board_credentials", "browserbase_settings", "model_credentials"):
        deletion_db.execute(f"CREATE TEMP TABLE {table} (user_id text)")
        deletion_db.execute(f"INSERT INTO {table} VALUES (%s), (%s)", (OWNER, OTHER))
    deletion_db.execute("CREATE TEMP TABLE checkpoints (thread_id text)")
    deletion_db.execute("INSERT INTO checkpoints VALUES ('owned'), ('other')")
    deletion_db.commit()
    assert billing_store.delete_user_data(OWNER)
    assert deletion_db.execute("SELECT session_id FROM resume_files").fetchall() == [("other",)]
    assert deletion_db.execute("SELECT id FROM sessions").fetchall() == [("other",)]
    assert deletion_db.execute("SELECT thread_id FROM checkpoints").fetchall() == [("other",)]
    for table in ("board_credentials", "browserbase_settings", "model_credentials"):
        assert deletion_db.execute(f"SELECT user_id FROM {table}").fetchall() == [(OTHER,)]


@pytest.mark.requires_postgres
def test_failed_artifact_deletion_rolls_back_the_entire_operation(deletion_db):
    deletion_db.execute("CREATE TEMP TABLE checkpoints (unexpected text)")
    deletion_db.commit()
    assert session_store.delete_session("owned", OWNER) is False
    assert deletion_db.execute("SELECT id FROM sessions WHERE id = 'owned'").fetchone()
    assert deletion_db.execute("SELECT session_id FROM resume_files WHERE session_id = 'owned'").fetchone()


@pytest.mark.requires_postgres
def test_account_deletion_clears_runtime_autopilot_schema_without_cascade(deletion_db):
    from backend.shared.autopilot_store import _CREATE_TABLES
    deletion_db.execute(_CREATE_TABLES.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE IF NOT EXISTS"))
    deletion_db.execute("""INSERT INTO autopilot_schedules (user_id, resume_text, resume_bytes, notification_email)
                          VALUES (%s, 'private resume', 'bytes', 'private@example.com'),
                                 (%s, 'other resume', 'other', 'other@example.com')""", (OWNER, OTHER))
    deletion_db.commit()
    assert billing_store.delete_user_data(OWNER)
    assert deletion_db.execute("SELECT user_id::text, resume_text, is_active FROM autopilot_schedules").fetchall() == [(OTHER, "other resume", True)]


@pytest.mark.requires_postgres
def test_prefetched_schedule_owner_check_rejects_orphans_and_other_owner(deletion_db, monkeypatch):
    from backend.shared import autopilot_store
    deletion_db.execute(autopilot_store._CREATE_TABLES.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE IF NOT EXISTS"))
    sid = deletion_db.execute("INSERT INTO autopilot_schedules (user_id) VALUES (%s) RETURNING id", (OWNER,)).fetchone()[0]
    deletion_db.commit()
    monkeypatch.setattr(autopilot_store, "_connect", lambda: nullcontext(deletion_db))
    assert autopilot_store.schedule_owner_exists(str(sid), OWNER)
    assert not autopilot_store.schedule_owner_exists(str(sid), OTHER)
    deletion_db.execute("DELETE FROM users WHERE id = %s", (OWNER,))
    assert not autopilot_store.schedule_owner_exists(str(sid), OWNER)


@pytest.mark.requires_postgres
def test_account_deletion_handles_agent_author_runtime_foreign_key(deletion_db):
    from backend.shared.agent_store import _CREATE_TABLES
    deletion_db.execute(_CREATE_TABLES.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE IF NOT EXISTS"))
    deletion_db.execute("""INSERT INTO agents (slug, name, description, category, author_user_id)
                          VALUES ('owned', 'Owned', 'Owned description', 'career', %s),
                                 ('other', 'Other', 'Other description', 'career', %s)""", (OWNER, OTHER))
    deletion_db.commit()
    assert billing_store.delete_user_data(OWNER)
    assert deletion_db.execute("SELECT slug, author_user_id::text FROM agents").fetchall() == [("other", OTHER)]


@pytest.mark.requires_postgres
@pytest.mark.parametrize("operation", ["session", "account"])
def test_deletion_rejects_running_sessions_without_erasing_any_data(deletion_db, operation):
    from backend.shared.data_deletion import ActiveWorkDeletionError
    deletion_db.execute("UPDATE sessions SET status = 'applying' WHERE id = 'owned'")
    deletion_db.commit()
    with pytest.raises(ActiveWorkDeletionError):
        if operation == "session":
            session_store.delete_session("owned", OWNER)
        else:
            billing_store.delete_user_data(OWNER)
    assert deletion_db.execute("SELECT id FROM users WHERE id = %s", (OWNER,)).fetchone()
    assert deletion_db.execute("SELECT session_id FROM resume_files WHERE session_id = 'owned'").fetchone()
