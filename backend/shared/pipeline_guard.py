"""One active pipeline task per session in the gateway process."""
import asyncio
import functools
import logging

logger = logging.getLogger(__name__)
_active: dict[str, asyncio.Task] = {}


def is_pipeline_active(session_id: str) -> bool:
    task = _active.get(session_id)
    return task is not None and not task.done()


def single_pipeline_run(function):
    @functools.wraps(function)
    async def guarded(session_id, *args, **kwargs):
        # No await between checking and claiming: atomic within the event loop.
        if is_pipeline_active(session_id):
            logger.info('Ignoring duplicate pipeline start for session %s', session_id)
            return
        task = asyncio.current_task()
        _active[session_id] = task
        try:
            return await function(session_id, *args, **kwargs)
        finally:
            if _active.get(session_id) is task:
                _active.pop(session_id, None)
    return guarded


async def cancel_pipeline(session_id: str) -> None:
    task = _active.get(session_id)
    if task is None or task.done():
        return
    task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=10)
    except (asyncio.CancelledError, TimeoutError):
        pass
