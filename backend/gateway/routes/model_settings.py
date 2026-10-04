"""Authenticated BYOK setup; secrets are never returned to the client."""
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from backend.gateway.deps import get_current_user
from backend.shared.model_access import is_server_model_owner, resolve_model_credentials, ModelAccessRequired
from backend.shared.model_key_store import get_model_key, save_model_key
from backend.shared.config import get_settings

router = APIRouter(prefix='/api/model', tags=['model-settings'])


class ModelSettingsUpdate(BaseModel):
    anthropic_api_key: str | None = Field(default=None, max_length=1024)


def public_settings(user_id: str):
    key = get_model_key(user_id)
    owner = is_server_model_owner(user_id)
    ready = True
    try:
        credentials = resolve_model_credentials(user_id)
        provider = credentials.provider
    except ModelAccessRequired:
        ready = False
        provider = get_settings().LLM_PROVIDER if owner else 'anthropic'
    settings = get_settings()
    if provider == 'anthropic':
        models = {'default': settings.ANTHROPIC_DEFAULT_MODEL, 'premium': settings.ANTHROPIC_PREMIUM_MODEL,
                  'light': settings.ANTHROPIC_LIGHT_MODEL, 'browser': settings.ANTHROPIC_BROWSER_MODEL}
    else:
        models = {'default': settings.OPENAI_DEFAULT_MODEL, 'premium': settings.OPENAI_PREMIUM_MODEL,
                  'light': settings.OPENAI_DEFAULT_MODEL, 'browser': settings.OPENAI_BROWSER_MODEL}
    budget = None
    if owner:
        from backend.shared.model_budget import configured_ledger, Ledger, MODEL
        try:
            path = configured_ledger()
            if path:
                summary = Ledger(path).usage_summary()
                money = lambda value: format(Decimal(value) / Decimal(1_000_000), '.6f')
                budget = {'status': 'available', 'currency': 'USD',
                          'cap': money(summary['limit_microusd']),
                          'settled': money(summary['settled_microusd']),
                          'reserved': money(summary['reserved_microusd']),
                          'remaining': money(summary['remaining_microusd'])}
                models = {role: MODEL for role in models}
            else:
                budget = {'status': 'not_configured'}
        except Exception:
            budget = {'status': 'unavailable'}
            ready = False
    return {
        'anthropic_key_set': bool(key),
        'anthropic_key_hint': f'…{key[-4:]}' if key else None,
        'provider': provider,
        'server_credentials_available': owner,
        'ready': ready,
        'funding': 'server_demo' if owner else 'own_keys',
        'models': models,
        'budget': budget,
    }


@router.get('/settings')
async def get_model_settings(request: Request):
    return public_settings(str(get_current_user(request)['id']))


@router.put('/settings')
async def update_model_settings(request: Request, body: ModelSettingsUpdate):
    user_id = str(get_current_user(request)['id'])
    if body.anthropic_api_key is not None:
        key = body.anthropic_api_key.strip()
        if key and (not key.startswith('sk-ant-') or any(c.isspace() for c in key)):
            raise HTTPException(status_code=400, detail='Enter a valid Anthropic API key.')
        if key and not is_server_model_owner(user_id) and key == get_settings().ANTHROPIC_API_KEY:
            raise HTTPException(status_code=403, detail='Use your own Anthropic API key.')
        save_model_key(user_id, key)
    return public_settings(user_id)
