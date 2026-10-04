"""Dashboard results must not describe an uncertain delivery as nothing sent."""
import pytest

from backend.tests.test_double_submit_prevention import _db_identity, _ensure_schema
from backend.shared.application_store import record_result
from backend.shared.session_store import get_sessions_for_user, update_session_counts

pytestmark = pytest.mark.requires_postgres


def test_session_list_separates_uncertain_delivery(_db_identity):
    session_id, user_id = _db_identity
    record_result(session_id, "confirmed", "submitted", user_id=user_id)
    record_result(session_id, "failed", "failed", user_id=user_id)
    record_result(session_id, "unknown", "failed", user_id=user_id,
                  error_category="submission_uncertain")
    update_session_counts(session_id, applications_submitted=1, applications_failed=2)
    result = next(s for s in get_sessions_for_user(user_id) if s["session_id"] == session_id)
    assert result["applications_uncertain"] == 1
    assert result["applications_failed"] == 1
    assert result["applications_submitted"] == 1


def test_legacy_counts_remain_without_result_rows(_db_identity):
    session_id, user_id = _db_identity
    update_session_counts(session_id, applications_submitted=2, applications_failed=3)
    result = next(s for s in get_sessions_for_user(user_id) if s["session_id"] == session_id)
    assert result["applications_uncertain"] == 0
    assert result["applications_failed"] == 3
    assert result["applications_submitted"] == 2
