"""Lazy access to the legacy browser engine, absent from Stagehand deployments."""
from importlib import import_module


class OptionalBrowserUnavailable(RuntimeError):
    pass


def require_browser_use():
    """Fail before creating a browser when the optional engine is unavailable."""
    try:
        return import_module('browser_use')
    except ImportError:
        raise OptionalBrowserUnavailable(
            'This browser feature is unavailable on this deployment. Indeed applications use Stagehand.'
        ) from None
