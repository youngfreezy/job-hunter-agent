"""Resolve model actions once; execute only the inspected native control."""
from dataclasses import dataclass
import json
import re

from backend.shared.application_rules import ApplicationParked


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


async def resolve_action(agent, page, instruction: str) -> GroundedAction:
    observed = await agent.observe(instruction + '\nReturn exactly one atomic action on a visible control. '
                                   'Use only click, fill, selectOption, check, or uncheck. '
                                   'Do not combine actions, press Enter, or return JavaScript.', page=page, cache=False)
    if len(observed.data) != 1:
        raise ApplicationParked('Could not identify one unambiguous control for the requested action.')
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
    snapshot = await page.snapshot(include_iframes=True)
    role, _ = _control(snapshot, action.selector)
    if method in ('check', 'uncheck') and (
            role not in ('checkbox', 'radio') or (role == 'radio' and method == 'uncheck')):
        raise ApplicationParked('The observed control is not a supported checkbox or radio button.')
    label = control_label(snapshot, action.selector)
    locator = page.locator(action.selector)
    if not label or await locator.count() != 1 or not await locator.is_visible():
        raise ApplicationParked('Could not verify the observed control in the current form.')
    return GroundedAction(action.selector, label, method, arguments)
