"""Delete owned data in the caller's transaction, including stores without FKs."""

from psycopg import Connection, sql


class ActiveWorkDeletionError(ValueError):
    """Workers must settle before their durable inputs can be erased."""


def require_stopped_sessions(rows: list[tuple]) -> None:
    if any(status not in ("completed", "failed") for _, status in rows):
        raise ActiveWorkDeletionError("Stop all active sessions before deleting their data.")


async def require_idle_sessions(user_id: str, session_ids: list[str], *, entire_account: bool = False) -> None:
    """Reject active or admitted work, including reservations in another process."""
    from backend.shared.pipeline_guard import is_pipeline_active
    from backend.shared.task_queue import get_queue_position, get_user_active_count

    if any(is_pipeline_active(sid) for sid in session_ids):
        raise ActiveWorkDeletionError("Stop all active sessions before deleting their data.")
    if entire_account:
        busy = await get_user_active_count(user_id) > 0
    else:
        busy = any([await get_queue_position(sid) >= 0 for sid in session_ids])
    if busy:
        raise ActiveWorkDeletionError("Stop queued and active sessions before deleting their data.")


def table_exists(conn: Connection, table: str) -> bool:
    """Check optional stores without putting the transaction into an error state."""
    return conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0] is not None


def delete_session_data(conn: Connection, session_ids: list[str]) -> None:
    """Delete children of already-authorized, locked sessions. Never commit here."""
    if not session_ids:
        return
    for table, key in (
        ("resume_files", "session_id"),
        ("failure_screenshots", "session_id"),
        ("skyvern_task_artifacts", "session_id"),
        ("session_outcomes", "session_id"),
        ("checkpoints", "thread_id"),
        ("checkpoint_blobs", "thread_id"),
        ("checkpoint_writes", "thread_id"),
        ("application_results", "session_id"),
        ("dead_letter_queue", "session_id"),
    ):
        if table_exists(conn, table):
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE {} = ANY(%s)").format(
                    sql.Identifier(table), sql.Identifier(key)),
                (session_ids,),
            )


def delete_user_children(conn: Connection, user_id: str) -> None:
    """Erase non-cascading owned stores before deleting the identity."""
    rows = conn.execute(
        "SELECT id, status FROM sessions WHERE user_id::text = %s FOR UPDATE", (str(user_id),)
    ).fetchall()
    require_stopped_sessions(rows)
    delete_session_data(conn, [str(row[0]) for row in rows])
    # Uploaded resumes need not have a session yet.
    if table_exists(conn, "resume_files"):
        conn.execute("DELETE FROM resume_files WHERE owner_user_id = %s", (str(user_id),))
    for table in ("board_credentials", "browserbase_settings", "model_credentials", "autopilot_schedules"):
        if table_exists(conn, table):
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE user_id::text = %s").format(sql.Identifier(table)),
                (str(user_id),),
            )
    if table_exists(conn, "agents"):
        conn.execute("DELETE FROM agents WHERE author_user_id = %s", (user_id,))
    conn.execute("DELETE FROM sessions WHERE user_id::text = %s", (str(user_id),))
