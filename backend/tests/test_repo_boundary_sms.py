"""Signed SMS callbacks pass CSRF and return well-formed, escaped TwiML."""

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.gateway.middleware.csrf import attach_csrf_protection
from backend.gateway.routes import sms


def test_signed_twilio_callback_reaches_signature_validation(monkeypatch):
    verify = MagicMock(return_value=True)
    monkeypatch.setattr(sms, "verify_twilio_signature", verify)
    monkeypatch.setattr(sms, "_handle_command", AsyncMock(return_value="Ready"))
    app = FastAPI()
    app.include_router(sms.router)
    attach_csrf_protection(app)
    response = TestClient(app).post("/api/sms/webhook", data={"From": "+15550000000", "Body": "HELP"})
    assert response.status_code == 200
    verify.assert_called_once()


def test_unsigned_twilio_callback_is_rejected(monkeypatch):
    monkeypatch.setattr(sms, "verify_twilio_signature", lambda *_: False)
    handler = AsyncMock()
    monkeypatch.setattr(sms, "_handle_command", handler)
    app = FastAPI()
    app.include_router(sms.router)
    attach_csrf_protection(app)
    response = TestClient(app).post("/api/sms/webhook", data={"Body": "APPROVE"})
    assert response.status_code == 403
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_sms_response_escapes_text_in_twiml(monkeypatch):
    from starlette.requests import Request
    monkeypatch.setattr(sms, "verify_twilio_signature", lambda *_: True)
    reply = 'Search for "R&D <platform>".'
    monkeypatch.setattr(sms, "_handle_command", AsyncMock(return_value=reply))
    request = Request({"type": "http", "scheme": "https", "path": "/api/sms/webhook", "headers": []})
    monkeypatch.setattr(request, "form", AsyncMock(return_value={"Body": "SEARCH R&D <platform>"}))
    response = await sms.twilio_webhook(request)
    assert ET.fromstring(response.body).find("Message").text == reply
