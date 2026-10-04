"""Uploaded file IDs must not authorize access across accounts."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.shared.models.schemas import StartSessionRequest


def test_cross_user_upload_is_rejected_before_launch(monkeypatch):
    from backend.gateway.routes.sessions import _load_owned_resume
    monkeypatch.setattr('backend.shared.resume_store.get_resume_for_user', lambda *_: None)
    with pytest.raises(HTTPException) as error:
        _load_owned_resume(StartSessionRequest(resume_uuid='other-upload'), 'attacker')
    assert error.value.status_code == 404


def test_owned_upload_ignores_client_supplied_file_path(monkeypatch):
    import tempfile
    from backend.gateway.routes.sessions import _load_owned_resume
    received = []
    def read(file_id, user_id):
        received.append((file_id, user_id)); return (b'owned-encrypted-file', '.pdf')
    monkeypatch.setattr('backend.shared.resume_store.get_resume_for_user', read)
    body = StartSessionRequest(resume_uuid='my-upload', resume_file_path=f'{tempfile.gettempdir()}/jobhunter_resumes/victim.pdf.enc')
    assert _load_owned_resume(body, 'me') == (b'owned-encrypted-file', '.pdf')
    assert body.resume_file_path is None
    assert received == [('my-upload', 'me')]


def test_text_only_search_has_no_file_capability():
    from backend.gateway.routes.sessions import _load_owned_resume
    assert _load_owned_resume(StartSessionRequest(resume_text='Own text'), 'me') is None


def test_resume_storage_failure_stops_before_launch(monkeypatch):
    from backend.gateway.routes.sessions import _load_owned_resume
    def unavailable(*_): raise RuntimeError('private database detail')
    monkeypatch.setattr('backend.shared.resume_store.get_resume_for_user', unavailable)
    with pytest.raises(HTTPException) as error:
        _load_owned_resume(StartSessionRequest(resume_uuid='my-upload'), 'me')
    assert error.value.status_code == 503
    assert 'private' not in error.value.detail


@pytest.mark.requires_postgres
def test_durable_resume_ownership_and_legacy_session_link():
    import uuid
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from backend.shared.db import get_connection
    from backend.shared import resume_store
    config = Config(str(Path(__file__).parents[1] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).parents[1] / 'alembic'))
    command.upgrade(config, 'head')
    owner = str(uuid.uuid4()); outsider = str(uuid.uuid4())
    upload = uuid.uuid4().hex; legacy = uuid.uuid4().hex
    try:
        resume_store.save_resume(upload, b'private', '.pdf', owner_user_id=owner)
        assert resume_store.get_resume_for_user(upload, owner) == (b'private', '.pdf')
        assert resume_store.get_resume_for_user(upload, outsider) is None
        resume_store.save_resume(legacy, b'legacy', '.pdf')
        assert resume_store.get_resume_for_user(legacy, owner) is None
        with get_connection() as conn:
            conn.execute('INSERT INTO users (id, email) VALUES (%s, %s)', (owner, f'{owner}@test.invalid'))
            conn.execute("INSERT INTO sessions (id, user_id, status) VALUES (%s, %s, 'completed')", (legacy, owner))
            conn.commit()
        assert resume_store.get_resume_for_user(legacy, owner) == (b'legacy', '.pdf')
        assert resume_store.get_resume_for_user(legacy, outsider) is None
    finally:
        resume_store.delete_resume(upload); resume_store.delete_resume(legacy)
        with get_connection() as conn:
            conn.execute('DELETE FROM sessions WHERE id = %s', (legacy,))
            conn.execute('DELETE FROM users WHERE id = %s', (owner,))
            conn.commit()
