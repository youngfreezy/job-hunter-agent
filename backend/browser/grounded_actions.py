"""Resolve model actions once; execute only the inspected native control."""
from dataclasses import dataclass
import json
import re

from backend.shared.application_rules import ApplicationParked
from backend.browser.stagehand_cache import record_result_cache, page_cache_options


class UnresolvedControl(ApplicationParked):
    """Observation found no unique target; no browser action was executed."""


def _control(snapshot, selector: str) -> tuple[str, str]:
    target = selector.removeprefix('xpath=')
    ids = {key for key, path in snapshot.xpath_map.items()
           if path.removeprefix('xpath=') == target}
    labels = []
    for line in snapshot.formatted_tree.splitlines():
        match = re.match(r'\s*\[([^]]+)\]\s+([^:]+):\s*(.*)', line)
        if match and match.group(1) in ids:
            labels.append((match.group(2).strip(), match.group(3)))
    return labels[0] if len(labels) == 1 else ('', '')


def control_label(snapshot, selector: str) -> str:
    return _control(snapshot, selector)[1]


@dataclass(frozen=True)
class GroundedAction:
    selector: str
    label: str
    method: str
    arguments: tuple[str, ...]

    @property
    def is_submission(self) -> bool:
        return self.method == 'click' and bool(re.search(
            r'\bsubmit\b|\b(send|finish|complete)\s+(?:this\s+|your\s+|the\s+)?application\b', self.label, re.I))

    def audit_text(self) -> str:
        return json.dumps({'observed_control': self.label, 'method': self.method,
                           'arguments': self.arguments})

    async def execute(self, page) -> None:
        # Freshly check the exact observed target. Never ask act() to reinterpret
        # an instruction or self-heal to another control after approval/claim.
        snapshot = await page.snapshot(include_iframes=True)
        if control_label(snapshot, self.selector) != self.label:
            raise ApplicationParked('The observed control changed; review the current form before continuing.')
        locator = page.locator(self.selector)
        if await locator.count() != 1 or not await locator.is_visible():
            raise ApplicationParked('The observed control is no longer unique and visible.')
        if self.method == 'click':
            await locator.click()
        elif self.method == 'fill':
            await locator.fill(self.arguments[0])
        elif self.method == 'selectOption':
            await locator.select_option(list(self.arguments))
        elif self.method in ('check', 'uncheck'):
            role, _ = _control(snapshot, self.selector)
            if role not in ('checkbox', 'radio') or (role == 'radio' and self.method == 'uncheck'):
                raise ApplicationParked('The observed control is not a supported checkbox or radio button.')
            expected = self.method == 'check'
            if await locator.is_checked() != expected:
                await locator.click()
            if await locator.is_checked() != expected:
                raise ApplicationParked('The checkbox or radio button did not reach its requested state.')
        else:
            raise ApplicationParked('Unsupported browser action; application was not advanced.')


def _validated_action(observed, snapshot) -> GroundedAction:
    if len(observed.data) != 1:
        raise UnresolvedControl('Could not identify one unambiguous control for the requested action.')
    action = observed.data[0]
    method = action.method
    arguments = tuple(action.arguments or ())
    # Native fill does not press Enter; type/press may submit a form implicitly.
    if method == 'type':
        method = 'fill'
    if (method not in ('click', 'fill', 'selectOption', 'check', 'uncheck')
            or (method in ('click', 'check', 'uncheck') and arguments)
            or (method == 'fill' and len(arguments) != 1)
            or (method == 'selectOption' and not arguments)):
        raise ApplicationParked('Unsupported browser action; application was not advanced.')
    role, label = _control(snapshot, action.selector)
    if not label:
        # The page can change after observe. No mutation has happened: let the
        # caller request one fresh Stagehand plan, not an applicant answer.
        raise UnresolvedControl('Could not verify the observed control in the current form.')
    if method in ('check', 'uncheck') and (
            role not in ('checkbox', 'radio') or (role == 'radio' and method == 'uncheck')):
        raise ApplicationParked('The observed control is not a supported checkbox or radio button.')
    return GroundedAction(action.selector, label, method, arguments)


async def resolve_action(agent, page, instruction: str, *, fresh: bool = False) -> GroundedAction:
    """Reuse observations, never action outcomes; validate the live target before acting."""
    prompt = instruction + '\nReturn exactly one atomic action on a visible control. ' \
        'Use only click, fill, selectOption, check, or uncheck. ' \
        'Do not combine actions, press Enter, or return JavaScript.'
    for attempt in range(2):
        url = await page.url()
        cache = await page_cache_options(page, instruction, fresh=fresh)
        before = await page.snapshot(include_iframes=True) if cache is not False or attempt else None
        observed = await agent.observe(prompt, page=page, cache=cache)
        metadata = record_result_cache(agent, 'observe', observed)
        hit = bool(metadata and metadata['status'] == 'HIT')
        try:
            snapshot = await page.snapshot(include_iframes=True)
            action = _validated_action(observed, snapshot)
            if (hit or attempt) and (before is None or await page.url() != url
                        or _control(before, action.selector) != _control(snapshot, action.selector)):
                raise UnresolvedControl('The cached control changed; a fresh observation is required.')
            locator = page.locator(action.selector)
            if await locator.count() != 1 or not await locator.is_visible():
                raise UnresolvedControl('The observed control is no longer unique and visible.')
        except ApplicationParked:
            if hit and not fresh and attempt == 0:
                fresh = True
                continue  # Read again once; no browser mutation has happened.
            raise
        if action.is_submission and cache is not False:
            fresh = True
            continue  # A planner's "act" can conceal the final submit control.
        return action
    raise UnresolvedControl('Could not resolve a fresh application control.')
