"""Discard Stagehand's mandatory trace export without ever reading its body."""

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

STAGEHAND_TELEMETRY_PATH = "/api/stagehand/v1/traces"


class StagehandTelemetryDiscard:
    """Exact-path ASGI sink, outside authentication and request instrumentation.

    Stagehand 4.1 has no telemetry opt-out. Its extension may include applicant
    prompts in spans. Never call receive(), parse, log, store, or forward them.
    A credential-free CORS response lets the extension export once successfully
    without broadening the application's existing authentication/CORS policy.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != STAGEHAND_TELEMETRY_PATH:
            await self.app(scope, receive, send)
            return
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "content-type, traceparent, tracestate",
            "Access-Control-Max-Age": "600",
            "Cache-Control": "no-store",
        }
        status = 204
        if scope["method"] not in ("POST", "OPTIONS"):
            status = 405
            headers["Allow"] = "POST, OPTIONS"
        await Response(status_code=status, headers=headers)(scope, receive, send)
