# steer-playwright

Standalone, steerable Playwright helper for form-driven browser automation.

## What this package provides
- Browser lifecycle management (`start`, `stop`, async context manager)
- Page navigation
- Visible form-field extraction (`input`, `textarea`, `select`)
- Fill-instruction planning (heuristic by default, pluggable custom analyser)
- Form filling/upload execution

This package is intentionally decoupled from `backend.*` project internals.

## Install

```bash
pip install -e .
```

From this folder (`steer-playwright/`), or publish to PyPI when ready.

## Quickstart

```python
import asyncio
from steer_playwright import Pilot

async def main():
    async with Pilot(headless=True) as pilot:
        page = await pilot.new_page()
        await pilot.navigate(page, "https://example.com")
        fields = await pilot.extract_fields(page)
        print("fields:", len(fields))

asyncio.run(main())
```

## LLM Integration

Pass a `custom_analyser(fields, resume_text, cover_letter)` function to
`analyse_fields` or `auto_fill` if you want model-driven fill strategies.

## License

MIT
