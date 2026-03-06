"""Quick test: navigate to real job pages and verify external link detection + auth wall detection."""
import asyncio
import sys
sys.path.insert(0, ".")

from backend.browser.manager import BrowserManager, apply_stealth
from backend.orchestrator.agents.application import (
    _find_external_apply_link,
    _has_auth_wall,
    _is_login_page,
)

# Real job URLs from different boards to test
TEST_URLS = [
    # ZipRecruiter — should detect auth wall or external link
    "https://www.ziprecruiter.com/jobs/WJxbvSRjmzRn86W11lIUcQ",
    # LinkedIn public job page
    "https://www.linkedin.com/jobs/view/4148007748",
    # Greenhouse direct (should work — public apply)
    "https://boards.greenhouse.io/figma/jobs/5327766004",
    # Lever direct (should work — public apply)
    "https://jobs.lever.co/anthropic",
]


async def test_url(context, url: str):
    print(f"\n{'='*60}")
    print(f"Testing: {url}")
    print(f"{'='*60}")

    page = await context.new_page()
    await apply_stealth(page)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        final_url = page.url
        title = await page.title()
        print(f"  Final URL: {final_url}")
        print(f"  Title: {title}")

        # Check login page
        is_login = _is_login_page(final_url)
        print(f"  Is login page (URL): {is_login}")

        # Check auth wall
        has_wall = await _has_auth_wall(page)
        print(f"  Has auth wall (text): {has_wall}")

        # Check external apply link
        ext_link = await _find_external_apply_link(page)
        print(f"  External apply link: {ext_link}")

        # Get page text snippet for debugging
        text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
        print(f"  Page text (first 500 chars):")
        for line in text.split("\n")[:10]:
            if line.strip():
                print(f"    {line.strip()}")

        # Check for any apply-like buttons
        apply_buttons = await page.evaluate("""() => {
            const btns = document.querySelectorAll('button, a');
            return Array.from(btns)
                .filter(b => b.innerText.toLowerCase().includes('apply'))
                .map(b => ({
                    tag: b.tagName,
                    text: b.innerText.trim().substring(0, 80),
                    href: b.href || null,
                    classes: b.className.substring(0, 80),
                }))
                .slice(0, 5);
        }""")
        if apply_buttons:
            print(f"  Apply buttons found:")
            for btn in apply_buttons:
                print(f"    <{btn['tag']}> '{btn['text']}' href={btn.get('href', 'none')}")
        else:
            print(f"  No apply buttons found on page")

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        await page.close()


async def main():
    manager = BrowserManager()
    await manager.start(headless=True)
    ctx_id, context = await manager.new_context()

    for url in TEST_URLS:
        await test_url(context, url)

    await manager.stop()
    print("\n\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
