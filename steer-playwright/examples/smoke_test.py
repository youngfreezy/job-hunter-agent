"""Live smoke test for steer-playwright."""

import asyncio

from steer_playwright import Pilot


async def main() -> None:
    async with Pilot(headless=True) as pilot:
        page = await pilot.new_page()
        await pilot.navigate(page, "https://example.com")
        title = await page.title()
        fields = await pilot.extract_fields(page)
        print("TITLE:", title)
        print("FIELDS:", len(fields))


if __name__ == "__main__":
    asyncio.run(main())
