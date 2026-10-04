# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Tests for double-submit prevention via pending records.

Verifies that:
1. Only confirmed or uncertain delivery blocks another submission
2. clear_pending removes only the pending record, not submitted ones
3. Failed/skipped records do NOT block re-attempts
4. The full lifecycle: pending → clear → final record works correctly
"""

import asyncio
import uuid
from pathlib import Path

import pytest
from backend.shared.application_store import (
    check_already_applied,
    clear_pending,
    ensure_table,
    record_result,
)
from backend.shared.db import get_connection

# Skipped with a reason by backend/tests/conftest.py when Postgres is down.
pytestmark = pytest.mark.requires_postgres


@pytest.fixture(autouse=True, scope="module")
def _ensure_schema():
    """Bring CI's fresh Postgres to the real schema before the module runs.

    The alembic chain creates users, sessions and application_results with
    the foreign keys production has; ensure_table() then adds the columns
    the store expects.  Both are idempotent.
    """
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(cfg, "head")
    asyncio.run(ensure_table())


@pytest.fixture()
def _db_identity():
    """Create a real user and session row for the test, then delete them.

    application_results.session_id references sessions(id) and sessions.user_id
    references users(id) once the alembic chain has run, so the rows under
    test must belong to a session that exists.  Deleting the user cascades
    to the session and to every application_results row created here.
    """
    user_id = str(uuid.uuid4())
    session_id = _unique_id()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email) VALUES (%s, %s)",
            (user_id, f"{session_id}@test.invalid"),
        )
        conn.execute(
            "INSERT INTO sessions (id, user_id, status) VALUES (%s, %s, 'intake')",
            (session_id, user_id),
        )
        conn.commit()
    yield session_id, user_id
    with get_connection() as conn:
        conn.execute("DELETE FROM application_results WHERE session_id = %s", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def _unique_id() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


class TestPendingBlocksDoubleSubmit:
    """Ordinary preparation permits retry; submitted delivery does not."""

    def test_pending_record_does_not_block_resubmit(self, _db_identity):
        """Pending records should NOT block re-attempts — only submitted does."""
        job_id = _unique_id()
        session_id, user_id = _db_identity

        # No prior record → should return None
        assert check_already_applied(job_id, user_id=user_id) is None

        # Insert pending record (simulates pre-Skyvern call)
        record_result(
            session_id=session_id,
            job_id=job_id,
            status="pending",
            job_title="Backend Engineer",
            job_company="Acme",
            job_url="https://example.com/job/1",
            user_id=user_id,
        )

        # Pending should NOT block — only submitted blocks
        assert check_already_applied(job_id, user_id=user_id) is None

    def test_submitted_blocks_resubmit(self, _db_identity):
        """Only submitted status should block re-attempts."""
        job_id = _unique_id()
        session_id, user_id = _db_identity
        url = f"https://example.com/job/{uuid.uuid4().hex[:8]}"

        record_result(
            session_id=session_id,
            job_id=job_id,
            status="submitted",
            job_title="Frontend Dev",
            job_url=url,
            user_id=user_id,
        )

        # Submitted should block by job_id
        result = check_already_applied(job_id, user_id=user_id)
        assert result is not None
        assert result["job_title"] == "Frontend Dev"

        # And by URL fallback with different job_id
        different_job_id = _unique_id()
        result = check_already_applied(different_job_id, user_id=user_id, job_url=url)
        assert result is not None


class TestClearPending:
    """clear_pending should remove only the pending record."""

    def test_clear_removes_pending_only(self, _db_identity):
        job_id = _unique_id()
        session_id, user_id = _db_identity

        # Insert pending then submitted
        record_result(
            session_id=session_id, job_id=job_id, status="pending",
            job_title="SRE", user_id=user_id,
        )

        # Clear pending — should remove the pending row
        clear_pending(session_id, job_id)

        # No submitted record exists, so should not block
        assert check_already_applied(job_id, user_id=user_id) is None

    def test_clear_does_not_remove_submitted(self, _db_identity):
        job_id = _unique_id()
        session_id, user_id = _db_identity

        # Insert submitted record
        record_result(
            session_id=session_id, job_id=job_id, status="submitted",
            job_title="SRE", user_id=user_id,
        )

        # clear_pending should NOT remove the submitted record
        clear_pending(session_id, job_id)
        assert check_already_applied(job_id, user_id=user_id) is not None


class TestFailedSkippedDontBlock:
    """Failed and skipped records should NOT block re-attempts."""

    @pytest.mark.parametrize("status", ["failed", "skipped"])
    def test_non_blocking_statuses(self, _db_identity, status):
        job_id = _unique_id()
        session_id, user_id = _db_identity

        record_result(
            session_id=session_id, job_id=job_id, status=status,
            job_title="DevOps", user_id=user_id,
        )

        # Should NOT block — only submitted/pending block
        assert check_already_applied(job_id, user_id=user_id) is None


class TestFullLifecycle:
    """Simulate the full pending → clear → final result lifecycle."""

    def test_pending_then_submitted(self, _db_identity):
        job_id = _unique_id()
        session_id, user_id = _db_identity

        # 1. Record pending (before Skyvern call)
        record_result(
            session_id=session_id, job_id=job_id, status="pending",
            job_title="ML Engineer", job_company="BigCo", user_id=user_id,
        )
        # Pending should not block
        assert check_already_applied(job_id, user_id=user_id) is None

        # 2. Clear pending (after Skyvern returns)
        clear_pending(session_id, job_id)

        # 3. Record final result
        record_result(
            session_id=session_id, job_id=job_id, status="submitted",
            job_title="ML Engineer", job_company="BigCo", user_id=user_id,
        )

        # Should still block (now via submitted record)
        result = check_already_applied(job_id, user_id=user_id)
        assert result is not None
        assert result["job_company"] == "BigCo"

    def test_pending_then_failed(self, _db_identity):
        job_id = _unique_id()
        session_id, user_id = _db_identity

        # 1. Record pending
        record_result(
            session_id=session_id, job_id=job_id, status="pending",
            job_title="Data Engineer", user_id=user_id,
        )

        # 2. Clear pending + record failure
        clear_pending(session_id, job_id)
        record_result(
            session_id=session_id, job_id=job_id, status="failed",
            job_title="Data Engineer", error_message="captcha_timeout",
            user_id=user_id,
        )

        # Should NOT block — failed allows retry
        assert check_already_applied(job_id, user_id=user_id) is None


@pytest.mark.parametrize("lookup_by_url", [False, True])
def test_uncertain_submission_blocks_new_session_until_reconciled(_db_identity, lookup_by_url):
    session_id, user_id = _db_identity
    job_id = _unique_id()
    url = f"https://www.indeed.com/viewjob?jk={job_id}"
    record_result(session_id=session_id, user_id=user_id, job_id=job_id,
                  job_url=url, status="failed", error_category="submission_uncertain",
                  error_message="Submit clicked but receipt not verified")
    prior = check_already_applied(_unique_id() if lookup_by_url else job_id,
                                 user_id=user_id, job_url=url)
    assert prior is not None
    assert prior["error_category"] == "submission_uncertain"
    assert prior["status"] == "failed"
    assert check_already_applied(job_id, user_id=str(uuid.uuid4()), job_url=url) is None


def test_submission_intent_survives_cleanup_and_retains_source_until_receipt(_db_identity):
    from backend.shared.application_store import mark_submission_intent
    session_id, user_id = _db_identity
    job_id = _unique_id()
    source_url = f"https://www.indeed.com/viewjob?jk={job_id}"
    record_result(session_id=session_id, user_id=user_id, job_id=job_id,
                  job_url=source_url, status="pending")
    mark_submission_intent(session_id, job_id)
    clear_pending(session_id, job_id)  # Also models cleanup following interrupted submission.
    prior = check_already_applied(job_id, user_id=user_id)
    assert prior['error_category'] == 'submission_uncertain'
    assert check_already_applied(_unique_id(), user_id=user_id, job_url=source_url)
    record_result(session_id=session_id, user_id=user_id, job_id=job_id,
                  job_url=source_url, status="submitted")
    prior = check_already_applied(job_id, user_id=user_id)
    assert prior['status'] == 'submitted'
    assert prior['error_category'] is None
    with get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM application_results WHERE session_id=%s AND job_id=%s",
                            (session_id, job_id)).fetchone()[0] == 1


def test_submission_intent_requires_existing_attempt(_db_identity):
    from backend.shared.application_store import mark_submission_intent
    session_id, _ = _db_identity
    with pytest.raises(RuntimeError, match='pending application'):
        mark_submission_intent(session_id, _unique_id())


def test_uncertain_final_result_atomically_replaces_intent(_db_identity):
    from backend.shared.application_store import mark_submission_intent
    session_id, user_id = _db_identity
    job_id = _unique_id()
    record_result(session_id=session_id, user_id=user_id, job_id=job_id, status='pending')
    mark_submission_intent(session_id, job_id)
    record_result(session_id=session_id, user_id=user_id, job_id=job_id,
                  status='failed', error_category='submission_uncertain')
    assert check_already_applied(job_id, user_id=user_id)['error_category'] == 'submission_uncertain'
    with get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM application_results WHERE session_id=%s AND job_id=%s",
                            (session_id, job_id)).fetchone()[0] == 1


@pytest.mark.parametrize('different_job_id', [False, True])
def test_concurrent_submission_claim_has_only_one_winner(_db_identity, different_job_id):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from backend.shared.application_store import mark_submission_intent

    session_id, user_id = _db_identity
    second_session = _unique_id()
    jobs = [_unique_id(), _unique_id()]
    if not different_job_id:
        jobs[1] = jobs[0]
    url = f'https://www.indeed.com/viewjob?jk={jobs[0]}'
    with get_connection() as conn:
        conn.execute("INSERT INTO sessions (id,user_id,status) VALUES (%s,%s,'applying')", (second_session, user_id))
        conn.commit()
    try:
        for sid, jid in zip([session_id, second_session], jobs):
            record_result(session_id=sid, user_id=user_id, job_id=jid, job_url=url, status='pending')
        barrier = Barrier(2)
        def claim(args):
            barrier.wait(timeout=5)
            try:
                mark_submission_intent(*args)
                return 'claimed'
            except RuntimeError as exc:
                assert 'previous submission' in str(exc).lower()
                return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(claim, zip([session_id, second_session], jobs)))
        assert sorted(outcomes) == ['blocked', 'claimed']
        with get_connection() as conn:
            count = conn.execute("SELECT count(*) FROM application_results WHERE user_id=%s AND error_category='submission_uncertain'", (user_id,)).fetchone()[0]
            assert count == 1
    finally:
        with get_connection() as conn:
            conn.execute('DELETE FROM application_results WHERE session_id=%s', (second_session,))
            conn.execute('DELETE FROM sessions WHERE id=%s', (second_session,))
            conn.commit()


def test_replaying_same_submission_intent_is_blocked(_db_identity):
    from backend.shared.application_store import mark_submission_intent
    session_id, user_id = _db_identity
    job_id = _unique_id()
    record_result(session_id=session_id, user_id=user_id, job_id=job_id, status='pending')
    mark_submission_intent(session_id, job_id)
    with pytest.raises(RuntimeError, match='previous submission'):
        mark_submission_intent(session_id, job_id)
    assert check_already_applied(job_id, user_id=user_id)['error_category'] == 'submission_uncertain'


def test_final_claim_rechecks_confirmed_delivery_after_preflight(_db_identity):
    from backend.shared.application_store import mark_submission_intent
    session_id, user_id = _db_identity
    job_id = _unique_id()
    record_result(session_id=session_id, user_id=user_id, job_id=job_id, status='pending')
    assert check_already_applied(job_id, user_id=user_id) is None
    record_result(session_id=session_id, user_id=user_id, job_id=job_id, status='submitted')
    with pytest.raises(RuntimeError, match='previous submission'):
        mark_submission_intent(session_id, job_id)
    assert check_already_applied(job_id, user_id=user_id)['status'] == 'submitted'
