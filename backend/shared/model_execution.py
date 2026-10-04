"""Run user-funded background work without inheriting another caller's identity."""
from collections.abc import Awaitable, Callable
from typing import TypeVar

from backend.shared.model_access import model_user_scope, require_model_access

T = TypeVar('T')


async def run_model_task(user_id: str | None, operation: Callable[[], Awaitable[T]]) -> T:
    # Pass an operation factory so a failed preflight leaves no unawaited task.
    with model_user_scope(str(user_id) if user_id else None):
        require_model_access(str(user_id) if user_id else None)
        return await operation()
