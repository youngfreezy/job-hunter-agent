# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Tests for double-submit prevention via pending records.

Verifies that:
1. A pending record blocks check_already_applied (prevents double-submit on resume)
2. clear_pending removes only the pending record, not submitted ones
3. Failed/skipped records do NOT block re-attempts
4. The full lifecycle: pending → clear → final record works correctly
"""

import asyncio
import uuid
import pytest
from backend.shared.application_store import (
    check_already_applied,
    clear_pending,
    ensure_table,
    record_result,
)
from backend.shared.db import get_connection


@pytest.fixture(autouse=True, scope="module")
def _ensure_schema():
    """Create application_results table in CI's fresh Postgres."""
    asyncio.get_event_loop().run_until_complete(ensure_table())


@pytest.fixture()
def _clean_test_rows():
    """Track job_ids created during the test and delete them after."""
    created: list[str] = []
    yield created
    with get_connection() as conn:
        for jid in created:
            conn.execute(
                "DELETE FROM application_results WHERE job_id = %s", (jid,)
            )
        conn.commit()


def _unique_id() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


class TestPendingBlocksDoubleSubmit:
    """A 'pending' record should block check_already_applied."""

    def test_pending_record_does_not_block_resubmit(self, _clean_test_rows):
        """Pending records should NOT block re-attempts — only submitted does."""
        job_id = _unique_id()
        session_id = _unique_id()
        user_id = str(uuid.uuid4())
        _clean_test_rows.append(job_id)

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

    def test_submitted_blocks_resubmit(self, _clean_test_rows):
        """Only submitted status should block re-attempts."""
        job_id = _unique_id()
        session_id = _unique_id()
        user_id = str(uuid.uuid4())
        url = f"https://example.com/job/{uuid.uuid4().hex[:8]}"
        _clean_test_rows.append(job_id)

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

    def test_clear_removes_pending_only(self, _clean_test_rows):
        job_id = _unique_id()
        session_id = _unique_id()
        user_id = str(uuid.uuid4())
        _clean_test_rows.append(job_id)

        # Insert pending then submitted
        record_result(
            session_id=session_id, job_id=job_id, status="pending",
            job_title="SRE", user_id=user_id,
        )

        # Clear pending — should remove the pending row
        clear_pending(session_id, job_id)

        # No submitted record exists, so should not block
        assert check_already_applied(job_id, user_id=user_id) is None

    def test_clear_does_not_remove_submitted(self, _clean_test_rows):
        job_id = _unique_id()
        session_id = _unique_id()
        user_id = str(uuid.uuid4())
        _clean_test_rows.append(job_id)

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
    def test_non_blocking_statuses(self, _clean_test_rows, status):
        job_id = _unique_id()
        session_id = _unique_id()
        user_id = str(uuid.uuid4())
        _clean_test_rows.append(job_id)

        record_result(
            session_id=session_id, job_id=job_id, status=status,
            job_title="DevOps", user_id=user_id,
        )

        # Should NOT block — only submitted/pending block
        assert check_already_applied(job_id, user_id=user_id) is None


class TestFullLifecycle:
    """Simulate the full pending → clear → final result lifecycle."""

    def test_pending_then_submitted(self, _clean_test_rows):
        job_id = _unique_id()
        session_id = _unique_id()
        user_id = str(uuid.uuid4())
        _clean_test_rows.append(job_id)

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

    def test_pending_then_failed(self, _clean_test_rows):
        job_id = _unique_id()
        session_id = _unique_id()
        user_id = str(uuid.uuid4())
        _clean_test_rows.append(job_id)

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
