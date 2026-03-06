"""Form Filler -- uses Claude to analyse and fill application forms via Playwright.

Given a page showing a job application form, this module:
1. Extracts the DOM structure of all visible form fields
2. Sends the field structure to Claude to determine the best fill values
3. Fills and interacts with each field using Playwright
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.shared.llm import build_llm, invoke_with_retry

logger = logging.getLogger(__name__)


# --- Pydantic models for structured output ---

class FillInstruction(BaseModel):
    """A single instruction for filling a form field."""
    selector: str = Field(description="CSS selector for the field")
    action: Literal["fill", "select", "check", "upload", "click", "react_select", "skip"] = Field(
        description="The action to perform on the field"
    )
    value: str = Field(default="", description="Value to fill, select, or use")
    field_name: str = Field(default="", description="Human-readable name of the field")


class FormAnalysisResult(BaseModel):
    """Result of analysing a job application form."""
    instructions: List[FillInstruction] = Field(
        description="List of fill instructions for each form field"
    )


FORM_ANALYSIS_PROMPT = """\
You are an expert at filling out job application forms. You are given:
1. A list of form fields extracted from a web page (label, type, name, required, options)
2. Resume text and cover letter for the applicant
3. Any known ATS-specific strategies

For each field, determine the best value to fill in.

CRITICAL: Fill as many fields as possible. Only use action "skip" as an absolute last resort — \
every skipped required field may cause the application to fail. Try to infer reasonable values \
from the resume, cover letter, and common defaults.

Rules:
- For text inputs, use appropriate values from the resume/cover letter
- For dropdowns (select), pick the best matching option VALUE (not text). Use the "value" field from options, not the display text
- For react-select fields (type "react-select"), use action "react_select". The options array lists the actual available choices. Set value to the EXACT text of the option you want to select (must match one of the provided options). If no options are listed, use short unambiguous text to search. Examples: "United States", "Yes", "No", "Decline To Self Identify"
- For checkboxes, set value to "true" if it should be checked
- For file uploads (type "file"), set action to "upload" with an empty value — the system provides the actual file path separately
- For "are you authorized to work" questions, always "Yes"
- For "do you need sponsorship" questions, default to "No" unless the resume explicitly indicates non-US origin
- For salary / compensation fields, provide a reasonable number (e.g. 100000 for mid-level, 150000 for senior)
- For "how did you hear about us" questions, answer "LinkedIn" or "Job Board"
- For gender/race/veteran/disability questions (EEO / voluntary self-ID), select "Decline to Self Identify" or similar opt-out
- For start date fields, provide a date 2 weeks from now
- For years of experience, extract from resume or estimate from work history
- For LinkedIn URL fields, check the resume for a LinkedIn profile link
- For website/portfolio fields, check resume or use ""
- For phone number, use the number from the resume
- For country/location, default to "United States" if unclear
- For "are you 18+" questions, always "Yes"
- For cover letter textareas, paste the provided cover letter
- For "additional information" or "anything else" textareas, leave empty (use action "fill" with value "")

Skip only when:
- The field asks for information that truly cannot be determined or inferred
- The field is not required AND you have no relevant information
"""


async def _discover_react_select_options(page: Any, selector: str) -> List[Dict[str, str]]:
    """Open a React Select dropdown, capture all visible options, then close it.

    Returns a list of dicts with keys: value, text.
    """
    try:
        el = await page.query_selector(selector)
        if not el:
            return []

        # Click to open the dropdown
        await el.click()
        await page.wait_for_timeout(400)

        # Capture all visible options from the dropdown menu
        # React Select renders options in a container with class *select__menu*
        options = await page.evaluate("""(inputSelector) => {
            // Find the React Select container from the input
            const input = document.querySelector(inputSelector);
            if (!input) return [];

            // Walk up to the select container
            const container = input.closest('[class*="select__container"], [class*="indicatorContainer"]')
                ?.closest('[class*="select__container"]')
                || input.closest('[class*="select"]');

            // Find the menu — it may be a sibling of the container or inside it
            let menu = container?.querySelector('[class*="select__menu"]');
            if (!menu) {
                // Menu might be rendered as a portal at document body level
                menu = document.querySelector('[class*="select__menu"]');
            }
            if (!menu) return [];

            const optionEls = menu.querySelectorAll('[class*="select__option"]');
            return Array.from(optionEls).map(o => ({
                value: o.textContent.trim(),
                text: o.textContent.trim(),
            }));
        }""", selector)

        # Close the dropdown by pressing Escape
        await el.press("Escape")
        await page.wait_for_timeout(200)

        return options or []
    except Exception as exc:
        logger.debug("Failed to discover options for %s: %s", selector, exc)
        # Try to close any open dropdown
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return []


async def extract_form_fields(page: Any) -> List[Dict[str, Any]]:
    """Extract all visible form fields from the current page.

    Returns a list of dicts with keys: selector, type, name, label, required, options.
    """
    fields = await page.evaluate("""() => {
        const fields = [];
        const inputs = document.querySelectorAll(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), ' +
            'textarea, select'
        );

        for (const el of inputs) {
            if (el.offsetParent === null) continue;  // skip hidden

            let label = '';
            // Check for associated label
            if (el.id) {
                const labelEl = document.querySelector(`label[for="${el.id}"]`);
                if (labelEl) label = labelEl.textContent.trim();
            }
            // Check parent label
            if (!label) {
                const parentLabel = el.closest('label');
                if (parentLabel) label = parentLabel.textContent.trim();
            }
            // Check aria-labelledby (used by React Select / Greenhouse)
            if (!label) {
                const labelledBy = el.getAttribute('aria-labelledby');
                if (labelledBy) {
                    const lblEl = document.getElementById(labelledBy);
                    if (lblEl) label = lblEl.textContent.trim();
                }
            }
            // Check aria-label
            if (!label) label = el.getAttribute('aria-label') || '';
            // Check placeholder
            if (!label) label = el.getAttribute('placeholder') || '';
            // Check preceding sibling text (common in custom forms)
            if (!label) {
                const prev = el.previousElementSibling;
                if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN' || prev.tagName === 'P' || prev.tagName === 'DIV')) {
                    const t = prev.textContent.trim();
                    if (t.length < 100) label = t;
                }
            }
            // Check parent container for label text (Greenhouse pattern)
            if (!label) {
                const wrapper = el.closest('.field, .form-group, [class*="field"], [data-field]');
                if (wrapper) {
                    const lbl = wrapper.querySelector('label, [class*="label"], legend');
                    if (lbl) label = lbl.textContent.trim();
                }
            }

            let options = [];
            if (el.tagName === 'SELECT') {
                options = Array.from(el.options).map(o => ({
                    value: o.value,
                    text: o.textContent.trim()
                }));
            }

            // Build a reliable CSS selector
            let selector = '';
            if (el.id) {
                selector = '#' + CSS.escape(el.id);
            } else if (el.name) {
                selector = `[name="${CSS.escape(el.name)}"]`;
            } else {
                // Fallback: use index
                const allOfType = Array.from(document.querySelectorAll(el.tagName));
                const idx = allOfType.indexOf(el);
                selector = `${el.tagName.toLowerCase()}:nth-of-type(${idx + 1})`;
            }

            // Detect React Select combobox inputs
            const isReactSelect = el.getAttribute('role') === 'combobox' &&
                !!el.closest('[class*="select__container"], [class*="select__control"]');
            const fieldType = isReactSelect ? 'react-select' : (el.type || el.tagName.toLowerCase());

            fields.push({
                selector: selector,
                type: fieldType,
                name: el.name || '',
                label: label.substring(0, 200),
                required: el.required || el.getAttribute('aria-required') === 'true',
                options: options.slice(0, 50),  // cap options
            });
        }
        return fields;
    }""")

    # Filter out unlabeled ghost inputs (React Select renders invisible sibling inputs)
    fields = [f for f in fields if f.get("label") or f.get("name") or f.get("type") in ("react-select", "file")]

    # Discover actual options for React Select fields by opening each dropdown
    react_fields = [f for f in fields if f.get("type") == "react-select"]
    if react_fields:
        logger.info("Discovering options for %d React Select fields...", len(react_fields))
        for field in react_fields:
            options = await _discover_react_select_options(page, field["selector"])
            if options:
                field["options"] = options
                logger.info("  %s: %d options discovered", field.get("label", field["selector"]), len(options))

    react_count = len(react_fields)
    logger.info("Extracted %d form fields from page (%d react-select)", len(fields), react_count)
    return fields


async def analyse_form(
    fields: List[Dict[str, Any]],
    resume_text: str,
    cover_letter: str,
    job_title: str = "",
    job_company: str = "",
    ats_strategy: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Send form fields to Claude for intelligent fill-value determination.

    Uses structured output (tool calling) to guarantee valid JSON responses.
    Returns a list of fill instructions.
    """
    llm = build_llm(model="claude-sonnet-4-6", max_tokens=4096, temperature=0.0)
    structured_llm = llm.with_structured_output(FormAnalysisResult)

    user_content = (
        f"## Job\nTitle: {job_title}\nCompany: {job_company}\n\n"
        f"## Form Fields\n```json\n{json.dumps(fields, indent=2)}\n```\n\n"
        f"## Resume\n{resume_text[:3000]}\n\n"
        f"## Cover Letter\n{cover_letter[:2000]}\n\n"
    )
    if ats_strategy:
        user_content += f"## ATS Strategy\n{ats_strategy}\n\n"

    result: FormAnalysisResult = await invoke_with_retry(structured_llm, [
        SystemMessage(content=FORM_ANALYSIS_PROMPT),
        HumanMessage(content=user_content),
    ])

    instructions = [instr.model_dump() for instr in result.instructions]
    logger.info("Claude produced %d fill instructions", len(instructions))
    return instructions


async def _dismiss_overlays(page: Any) -> None:
    """Dismiss modal overlays that might intercept clicks on form fields."""
    overlay_selectors = [
        'div.modal__overlay--visible',
        'div[class*="modal__overlay"]',
        'div[class*="overlay"][class*="visible"]',
        'button[aria-label="Dismiss"]',
        'button[aria-label="Close"]',
        'button[data-test-modal-close-btn]',
    ]
    for sel in overlay_selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                # If it's a button, click it to dismiss; otherwise ignore
                tag = await el.evaluate("el => el.tagName")
                if tag == "BUTTON":
                    await el.click()
                    await page.wait_for_timeout(300)
                    logger.info("Dismissed overlay via %s", sel)
        except Exception:
            continue


async def fill_form(
    page: Any,
    instructions: List[Dict[str, Any]],
    resume_file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute fill instructions on the page.

    Parameters
    ----------
    page:
        The Playwright Page with the form visible.
    instructions:
        Output from ``analyse_form``.
    resume_file_path:
        Path to the resume file for upload fields.

    Returns
    -------
    dict
        Summary with keys: filled, skipped, errors.
    """
    filled = 0
    skipped = 0
    errors: List[str] = []

    # Dismiss any modal overlays before starting form fill
    await _dismiss_overlays(page)

    for instr in instructions:
        selector = instr.get("selector", "")
        action = instr.get("action", "skip")
        value = instr.get("value", "")
        field_name = instr.get("field_name", selector)

        if action == "skip":
            skipped += 1
            continue

        try:
            el = await page.query_selector(selector)
            if not el:
                logger.debug("Selector not found: %s", selector)
                skipped += 1
                continue

            if action == "fill":
                # Use force=True to bypass overlay interception (e.g. LinkedIn
                # Easy Apply modal has a background overlay that intercepts).
                try:
                    await el.click(force=True)
                except Exception:
                    pass  # click failed, but fill below may still work
                await el.fill("")
                await el.fill(str(value))
                filled += 1

            elif action == "select":
                try:
                    await el.select_option(value=str(value))
                except Exception:
                    # Fallback: try matching by label text instead of value
                    try:
                        await el.select_option(label=str(value))
                    except Exception:
                        raise
                filled += 1

            elif action == "check":
                if str(value).lower() in ("true", "yes", "1"):
                    await el.check(force=True)
                else:
                    await el.uncheck(force=True)
                filled += 1

            elif action == "upload":
                if resume_file_path:
                    await el.set_input_files(resume_file_path)
                    filled += 1
                else:
                    skipped += 1

            elif action == "react_select":
                # React Select: click → clear → type value → select option
                await el.click()
                await page.wait_for_timeout(300)
                await el.fill("")
                await page.wait_for_timeout(100)
                await el.fill(str(value))
                await page.wait_for_timeout(600)

                # Try to click the exact matching option text first
                option_clicked = False
                try:
                    option_el = page.locator(
                        f'[class*="select__option"]:has-text("{value}")'
                    ).first
                    if await option_el.is_visible(timeout=1000):
                        await option_el.click()
                        option_clicked = True
                except Exception:
                    pass

                if not option_clicked:
                    # Fallback: ArrowDown + Enter
                    await el.press("ArrowDown")
                    await page.wait_for_timeout(200)
                    await el.press("Enter")

                await page.wait_for_timeout(300)
                filled += 1

            elif action == "click":
                await el.click(force=True)
                filled += 1

            else:
                skipped += 1

            # Small delay between field fills to appear human-like
            import random
            await page.wait_for_timeout(random.randint(200, 800))

        except Exception as exc:
            error_msg = f"Failed to fill {field_name}: {exc}"
            logger.warning(error_msg)
            errors.append(error_msg)

    result = {"filled": filled, "skipped": skipped, "errors": errors}
    logger.info(
        "Form fill complete: %d filled, %d skipped, %d errors",
        filled, skipped, len(errors),
    )
    return result
