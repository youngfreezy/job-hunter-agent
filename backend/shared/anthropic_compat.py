"""Claude 5.5 request compatibility for the installed LangChain adapter.

https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5
https://platform.claude.com/docs/en/build-with-claude/structured-outputs
"""
from langchain_anthropic import ChatAnthropic


LATEST_MODELS = frozenset({'claude-sonnet-5-5', 'claude-opus-5-5'})


def model_options(model: str, temperature: float) -> dict:
    if model == 'claude-sonnet-5-5':
        # Bounded output still includes any thinking tokens. Medium is the
        # documented starting point for latency-sensitive, multistep tool use.
        return {'thinking': {'type': 'between_tools'}, 'effort': 'medium'}
    if model == 'claude-opus-5-5':
        return {}  # Adaptive thinking is the provider default; no sampling knobs.
    return {'temperature': temperature}


class CompatibleChatAnthropic(ChatAnthropic):
    def with_structured_output(self, schema, *, include_raw=False, method=None, **kwargs):
        if self.model in LATEST_MODELS:
            if method not in (None, 'json_schema'):
                raise ValueError('Claude 5.5 structured output requires json_schema.')
            method = 'json_schema'
        return super().with_structured_output(
            schema, include_raw=include_raw, method=method or 'function_calling', **kwargs,
        )

    def _get_request_payload(self, *args, **kwargs):
        payload = super()._get_request_payload(*args, **kwargs)
        if self.model not in LATEST_MODELS:
            return payload
        # The installed adapter emits the former beta shape. Translate to GA
        # without changing schema transformation, parsing or usage accounting.
        if 'output_format' in payload:
            config = dict(payload.get('output_config') or {})
            config['format'] = payload.pop('output_format')
            payload['output_config'] = config
        for option in ('temperature', 'top_p', 'top_k'):
            payload.pop(option, None)
        betas = [beta for beta in payload.get('betas', []) if beta not in {
            'structured-outputs-2025-11-13', 'effort-2025-11-24',
        }]
        # This installed SDK only accepts output_config on its beta writer.
        # Keep an empty list so LangChain selects that writer without enabling
        # a feature beta; removing the key routes to an incompatible signature.
        payload['betas'] = betas
        if (payload.get('tool_choice') or {}).get('type') in {'any', 'tool'}:
            raise ValueError('Claude 5.5 does not support forced tool use.')
        return payload
