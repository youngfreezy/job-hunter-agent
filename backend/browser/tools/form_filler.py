"""Form Filler -- uses Claude to analyse and fill application forms via Playwright.

Given a page showing a job application form, this module:
1. Extracts the DOM structure of all visible form fields
2. Sends the field structure to Claude to determine the best fill values
3. Fills and interacts with each field using Playwright
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from backend.shared.config import settings

logger = logging.getLogger(__name__)

FORM_ANALYSIS_PROMPT = """\
You are an expert at filling out job application forms.  You are given:
1. A list of form fields extracted from a web page (label, type, name, required, options)
2. Resume text and cover letter for the applicant
3. Any known ATS-specific strategies

For each field, return the best value to fill in.  Return ONLY valid JSON
with this structure:
[
  {
    "selector": "<CSS selector for the field>",
    "action": "fill" | "select" | "check" | "upload" | "click",
    "value": "<value to fill or select>",
    "field_name": "<human-readable name>"
  }
]

Rules:
- For text inputs, use appropriate values from the resume/cover letter
- For dropdowns (select), pick the best matching option value
- For checkboxes, set value to "true" if it should be checked
- For file uploads, set action to "upload" and value to the file path
- For "are you authorized to work" questions, always "Yes"
- For "do you need sponsorship" questions, answer based on resume context
- For salary fields, provide a reasonable number based on the job
- Skip fields you cannot determine (return them with action "skip")
- Return ONLY the JSON array -- no markdown, no explanation
"""


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
            // Check aria-label
            if (!label) label = el.getAttribute('aria-label') || '';
            // Check placeholder
            if (!label) label = el.getAttribute('placeholder') || '';

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

            fields.push({
                selector: selector,
                type: el.type || el.tagName.toLowerCase(),
                name: el.name || '',
                label: label.substring(0, 200),
                required: el.required || el.getAttribute('aria-required') === 'true',
                options: options.slice(0, 50),  // cap options
            });
        }
        return fields;
    }""")

    logger.info("Extracted %d form fields from page", len(fields))
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

    Returns a list of fill instructions.
    """
    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=4096,
        temperature=0.0,
    )

    user_content = (
        f"## Job\nTitle: {job_title}\nCompany: {job_company}\n\n"
        f"## Form Fields\n```json\n{json.dumps(fields, indent=2)}\n```\n\n"
        f"## Resume\n{resume_text[:3000]}\n\n"
        f"## Cover Letter\n{cover_letter[:2000]}\n\n"
    )
    if ats_strategy:
        user_content += f"## ATS Strategy\n{ats_strategy}\n\n"

    response = await llm.ainvoke([
        SystemMessage(content=FORM_ANALYSIS_PROMPT),
        HumanMessage(content=user_content),
    ])

    raw = response.content
    if isinstance(raw, list):
        raw = "".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in raw
        )

    instructions = json.loads(raw)
    logger.info("Claude produced %d fill instructions", len(instructions))
    return instructions


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
                await el.click()
                await el.fill("")
                await el.fill(str(value))
                filled += 1

            elif action == "select":
                await el.select_option(value=str(value))
                filled += 1

            elif action == "check":
                if str(value).lower() in ("true", "yes", "1"):
                    await el.check()
                else:
                    await el.uncheck()
                filled += 1

            elif action == "upload":
                file_path = resume_file_path if resume_file_path else str(value)
                if file_path:
                    await el.set_input_files(file_path)
                    filled += 1
                else:
                    skipped += 1

            elif action == "click":
                await el.click()
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
