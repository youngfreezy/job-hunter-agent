"""Bounded viewport inspection; it cannot click, fill, or submit a form."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from backend.browser.stagehand_budget import budget_stop_message
from backend.browser.stagehand_cache import record_result_cache

logger = logging.getLogger(__name__)
INSPECTION_TIMEOUT_SECONDS = 60
DIAGNOSTIC_TIMEOUT_SECONDS = 10
SCROLL_QUIET_SCRIPT = """(() => new Promise(resolve => {
  let idleTimer, maxTimer;
  const finish = value => {
    document.removeEventListener('scroll', changed, true);
    clearTimeout(idleTimer);
    clearTimeout(maxTimer);
    resolve(value);
  };
  const changed = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => finish(true), 200);
  };
  document.addEventListener('scroll', changed, {capture: true, passive: true});
  maxTimer = setTimeout(() => finish(false), 2000);
  changed();
}))()"""


async def inspect_verification_view(agent, page, *, prompt: str, schema: type,
                                    expected_url: str, guard: Callable[[], None], deadline: float):
    """At most one observe and one visual extract; caller owns the one-use limit.

    This changes only the viewport using Stagehand's chosen scroll container.
    A lower viewport is additional evidence, never proof of accepted verification.
    """
    page_id = getattr(page, 'page_id', None)
    remaining = min(INSPECTION_TIMEOUT_SECONDS, deadline - asyncio.get_running_loop().time())
    if not isinstance(page_id, str) or not page_id or remaining <= 0:
        return None

    async def unchanged():
        guard()
        current = await agent.browser.context.active_page()
        same = getattr(current, 'page_id', None) == page_id and await page.url() == expected_url
        guard()
        return same

    try:
        async with asyncio.timeout(remaining):
            if not await unchanged():
                return None
            observed = await agent.observe(
                'Inspect the application review without changing its answers. Find the unique scrollable '
                'container holding the review and return exactly one scrollTo action with argument "100%" '
                'to reveal its lower section. Do not click, fill, submit, navigate, or operate a verification '
                'widget. Return no actions if there is no unambiguous scroll container.',
                page=page, cache=False,
            )
            record_result_cache(agent, 'observe', observed)
            if not await unchanged() or len(observed.data) != 1:
                return None
            action = observed.data[0]
            arguments = action.arguments or ()
            if (action.method != 'scrollTo' or len(arguments) != 1
                    or arguments[0] not in ('100', '100%', 100)
                    or not isinstance(action.selector, str) or not action.selector.strip()):
                return None
            locator = page.locator(action.selector)
            if await locator.count() != 1 or not await locator.is_visible() or not await unchanged():
                return None
            guard()  # Last synchronous check before dispatching the sole scroll command.
            await locator.scroll_to(100)
            # SDK scroll_to uses smooth scrolling and can return before movement.
            # This observes document scroll events only; it operates no controls.
            if await page.evaluate(SCROLL_QUIET_SCRIPT) is not True:
                return None
            if not await unchanged():
                return None
            result = await agent.extract(
                prompt + '\nThe viewport was scrolled once to inspect the lower application review. '
                'Use this additional screenshot with the form evidence; absence of a challenge in this '
                'viewport does not prove verification was accepted. Do not infer or skip required answers.',
                schema, page=page, screenshot=True, cache=False,
            )
            record_result_cache(agent, 'extract', result)
            return result if await unchanged() else None
    except Exception as exc:
        if budget_stop_message(exc):
            raise
        # Cancellation is a BaseException and must propagate, as must budget stops.
        logger.info('Verification viewport inspection stopped (%s)', type(exc).__name__)
        return None


async def capture_verification_timeout(capture: Callable[[], Awaitable[object]]) -> None:
    """Use the existing owned screenshot store without delaying failure indefinitely."""
    try:
        await asyncio.wait_for(capture(), timeout=DIAGNOSTIC_TIMEOUT_SECONDS)
    except Exception as exc:
        if budget_stop_message(exc):
            raise
        logger.info('Verification timeout screenshot unavailable (%s)', type(exc).__name__)
