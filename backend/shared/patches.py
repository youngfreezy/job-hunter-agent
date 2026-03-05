"""Monkey-patches for third-party library bugs.

Import this module early (e.g. in gateway/main.py) to apply fixes.
"""

from __future__ import annotations


def _patch_anthropic_by_alias() -> None:
    """Fix anthropic SDK passing by_alias=None to Pydantic v2 model_dump.

    anthropic._compat.model_dump passes by_alias=None which Pydantic v2
    rejects with: "argument 'by_alias': 'NoneType' object cannot be
    converted to 'PyBool'". This wraps the function to convert None -> False.
    """
    try:
        import anthropic._compat as compat

        original = compat.model_dump

        def patched_model_dump(model, **kwargs):
            if "by_alias" in kwargs and kwargs["by_alias"] is None:
                kwargs["by_alias"] = False
            return original(model, **kwargs)

        compat.model_dump = patched_model_dump
    except Exception:
        pass


def apply_all() -> None:
    """Apply all patches."""
    _patch_anthropic_by_alias()
