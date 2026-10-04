"""Bind inference to an authenticated owner without checkpointing credentials."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from fastapi import HTTPException
from backend.shared.config import get_settings

_model_user: ContextVar[str | None] = ContextVar('jobhunter_model_user', default=None)


class ModelAccessRequired(HTTPException):
    def __init__(self, message='Add your Anthropic API key in Settings before starting.'):
        super().__init__(status_code=428, detail=message)


@dataclass(frozen=True)
class ModelCredentials:
    provider: str
    api_key: str = field(repr=False)
    server_funded: bool = False
    workspace_id: str | None = None


def current_model_user() -> str | None:
    return _model_user.get()


def bind_model_user(user_id: str | None) -> None:
    _model_user.set(str(user_id) if user_id else None)


@contextmanager
def model_user_scope(user_id: str | None):
    token = _model_user.set(str(user_id) if user_id else None)
    try:
        yield
    finally:
        _model_user.reset(token)


def is_server_model_owner(user_id: str | None) -> bool:
    owner = get_settings().BROWSERBASE_CONTEXT_USER_ID
    return bool(user_id and owner and str(user_id) == str(owner))


def model_provider_for_context() -> str:
    user_id = current_model_user()
    if user_id and not is_server_model_owner(user_id):
        return 'anthropic'
    return (get_settings().LLM_PROVIDER or 'openai').strip().lower()


def resolve_model_credentials(user_id: str | None) -> ModelCredentials:
    if not user_id:
        raise ModelAccessRequired('Sign in before using model-powered features.')
    settings = get_settings()
    if is_server_model_owner(user_id):
        provider = (settings.LLM_PROVIDER or 'openai').strip().lower()
        key = settings.ANTHROPIC_API_KEY if provider == 'anthropic' else settings.OPENAI_API_KEY
        if provider not in ('anthropic', 'openai') or not key:
            raise ModelAccessRequired('The demo owner model provider is not configured.')
        return ModelCredentials(provider, key, True, settings.ANTHROPIC_WORKSPACE_ID if provider == 'anthropic' else None)
    from backend.shared.model_key_store import get_model_key
    try:
        key = get_model_key(str(user_id))
    except Exception:
        raise ModelAccessRequired('Model key storage is temporarily unavailable.') from None
    if not key or key == settings.ANTHROPIC_API_KEY:
        raise ModelAccessRequired()
    return ModelCredentials('anthropic', key)


def current_model_credentials() -> ModelCredentials:
    return resolve_model_credentials(current_model_user())


def require_model_access(user_id: str) -> None:
    resolve_model_credentials(user_id)
