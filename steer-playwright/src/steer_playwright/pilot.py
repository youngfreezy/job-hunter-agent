"""Standalone steerable browser automation helper."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from patchright.async_api import Browser, BrowserContext, Playwright, async_playwright


Field = Dict[str, Any]
Instruction = Dict[str, Any]


def _guess_field_value(field: Field, resume_text: str, cover_letter: str) -> str:
    """Heuristic fallback value picker for common application fields."""
    label = f"{field.get('label', '')} {field.get('name', '')} {field.get('placeholder', '')}".lower()
    input_type = (field.get("type") or "").lower()

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", resume_text)
    phone_match = re.search(r"[\+]?[\d\s\-\(\)]{10,}", resume_text)
    first_line = (resume_text.strip().splitlines() or [""])[0].strip()
    name = first_line if first_line and "@" not in first_line else "Applicant"

    if "email" in label or input_type == "email":
        if not email_match:
            raise ValueError(
                "No email address found in your resume. "
                "Please add your email to your resume and try again."
            )
        return email_match.group(0)
    if "phone" in label or "mobile" in label or input_type == "tel":
        if not phone_match:
            raise ValueError(
                "No phone number found in your resume. "
                "Please add your phone number to your resume and try again."
            )
        return phone_match.group(0).strip()
    if "name" in label:
        return name
    if "linkedin" in label:
        return ""
    if "github" in label:
        return ""
    if "cover letter" in label and cover_letter:
        return cover_letter
    if "salary" in label or "compensation" in label:
        return ""
    if "sponsor" in label or "visa" in label:
        return "No"
    if "authorized" in label or "eligible" in label:
        return "Yes"
    if "location" in label or "city" in label:
        return ""
    if field.get("required"):
        return "N/A"
    return ""


class Pilot:
    """High-level, standalone browser automation helper.

    This class intentionally avoids project-specific imports so it can be
    extracted and published independently.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "Pilot":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context()

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    async def new_page(self) -> Any:
        if self._context is None:
            raise RuntimeError("Pilot not started. Call start() first.")
        return await self._context.new_page()

    async def navigate(self, page: Any, url: str, wait_until: str = "domcontentloaded") -> None:
        await page.goto(url, wait_until=wait_until, timeout=30000)

    async def extract_fields(self, page: Any) -> List[Field]:
        """Extract visible input/select/textarea metadata from current page."""
        return await page.evaluate(
            """() => {
              const fields = [];
              const nodes = document.querySelectorAll("input, textarea, select");
              for (const el of nodes) {
                if (!(el instanceof HTMLElement)) continue;
                if (el.offsetParent === null) continue;
                if (el instanceof HTMLInputElement && (el.type === "hidden" || el.type === "submit")) continue;

                let label = "";
                if (el.id) {
                  const l = document.querySelector(`label[for="${el.id}"]`);
                  if (l) label = (l.textContent || "").trim();
                }
                if (!label) {
                  const parentLabel = el.closest("label");
                  if (parentLabel) label = (parentLabel.textContent || "").trim();
                }

                fields.push({
                  tag: el.tagName.toLowerCase(),
                  type: (el instanceof HTMLInputElement) ? el.type : el.tagName.toLowerCase(),
                  id: el.id || "",
                  name: el.getAttribute("name") || "",
                  label,
                  placeholder: el.getAttribute("placeholder") || "",
                  required: el.hasAttribute("required") || el.getAttribute("aria-required") === "true",
                  selector: el.id ? `#${el.id}` : (el.getAttribute("name") ? `[name="${el.getAttribute("name")}"]` : "")
                });
              }
              return fields.filter(f => f.selector);
            }"""
        )

    async def analyse_fields(
        self,
        fields: List[Field],
        resume_text: str,
        cover_letter: str = "",
        custom_analyser: Optional[Callable[[List[Field], str, str], List[Instruction]]] = None,
    ) -> List[Instruction]:
        """Build fill instructions for fields.

        If ``custom_analyser`` is provided, it is used to generate the
        instructions (for example an LLM-driven analyser). Otherwise, a
        deterministic heuristic strategy is used.
        """
        if custom_analyser is not None:
            return custom_analyser(fields, resume_text, cover_letter)

        instructions: List[Instruction] = []
        for field in fields:
            value = _guess_field_value(field, resume_text, cover_letter)
            if not value:
                continue
            instructions.append(
                {
                    "selector": field["selector"],
                    "action": "fill",
                    "value": value,
                }
            )
        return instructions

    async def fill(
        self,
        page: Any,
        instructions: List[Instruction],
        resume_file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute fill/upload instructions on a page."""
        filled = 0
        skipped = 0
        errors: List[str] = []

        for ins in instructions:
            selector = ins.get("selector")
            action = ins.get("action", "fill")
            value = ins.get("value", "")
            if not selector:
                skipped += 1
                continue

            try:
                el = await page.query_selector(selector)
                if el is None:
                    skipped += 1
                    continue

                if action == "upload" and resume_file_path:
                    await el.set_input_files(resume_file_path)
                else:
                    await el.fill(value)
                filled += 1
            except Exception as exc:
                errors.append(f"{selector}: {exc}")

        return {"filled": filled, "skipped": skipped, "errors": errors}

    async def auto_fill(
        self,
        page: Any,
        resume_text: str,
        cover_letter: str = "",
        resume_file_path: Optional[str] = None,
        custom_analyser: Optional[Callable[[List[Field], str, str], List[Instruction]]] = None,
    ) -> Dict[str, Any]:
        fields = await self.extract_fields(page)
        instructions = await self.analyse_fields(
            fields=fields,
            resume_text=resume_text,
            cover_letter=cover_letter,
            custom_analyser=custom_analyser,
        )
        return await self.fill(
            page=page,
            instructions=instructions,
            resume_file_path=resume_file_path,
        )
