"""Debug the candidate-location React Select autocomplete field."""
import asyncio
import os

async def main():
    from patchright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"])
        ctx = await browser.new_context()
        page = await ctx.new_page()

        await page.goto("https://job-boards.greenhouse.io/airtable/jobs/8403058002",
                        wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        btn = await page.wait_for_selector('button:has-text("Apply")', timeout=5000)
        if btn:
            await btn.click()
        await asyncio.sleep(3)

        # Inspect the field
        info = await page.evaluate("""() => {
            const el = document.querySelector('#candidate-location');
            if (!el) return {error: 'not found'};
            const container = el.closest('[class]') || el.parentElement;
            return {
                tag: el.tagName,
                type: el.type,
                className: el.className,
                parentClass: container ? container.className : '',
                role: el.getAttribute('role'),
                ariaAuto: el.getAttribute('aria-autocomplete'),
                placeholder: el.placeholder || '',
            };
        }""")
        print("Field info:", info)

        # Try typing and wait for results
        el = await page.query_selector('#candidate-location')
        if not el:
            print("candidate-location not found!")
            await browser.close()
            return

        await el.click()
        await asyncio.sleep(0.3)
        await page.keyboard.type("Austin, TX", delay=50)
        await asyncio.sleep(2)

        # Check what appeared
        results = await page.evaluate("""() => {
            return {
                select_menu: !!document.querySelector('[class*="select__menu"]'),
                select_option_count: document.querySelectorAll('[class*="select__option"]').length,
                select_option_texts: [...document.querySelectorAll('[class*="select__option"]')].slice(0, 5).map(o => o.textContent.trim()),
                listbox: !!document.querySelector('[role="listbox"]'),
                option_count: document.querySelectorAll('[role="option"]').length,
                pac_container: !!document.querySelector('.pac-container'),
                loading: !!document.querySelector('[class*="loading"]'),
                no_options: document.querySelector('[class*="no-options"]') ? document.querySelector('[class*="no-options"]').textContent : null,
            };
        }""")
        print("After typing 'Austin, TX':", results)

        # Try just "Austin"
        await el.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await page.keyboard.type("Austin", delay=50)
        await asyncio.sleep(2)

        results2 = await page.evaluate("""() => {
            return {
                select_option_count: document.querySelectorAll('[class*="select__option"]').length,
                select_option_texts: [...document.querySelectorAll('[class*="select__option"]')].slice(0, 5).map(o => o.textContent.trim()),
                no_options: document.querySelector('[class*="no-options"]') ? document.querySelector('[class*="no-options"]').textContent : null,
                loading: !!document.querySelector('[class*="loadingIndicator"], [class*="loading"]'),
            };
        }""")
        print("After typing 'Austin':", results2)

        # Try clearing and pressing ArrowDown
        await el.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await page.keyboard.press("ArrowDown")
        await asyncio.sleep(1)

        results3 = await page.evaluate("""() => {
            return {
                select_option_count: document.querySelectorAll('[class*="select__option"]').length,
                no_options: document.querySelector('[class*="no-options"]') ? document.querySelector('[class*="no-options"]').textContent : null,
                menu: !!document.querySelector('[class*="select__menu"]'),
            };
        }""")
        print("After ArrowDown (empty):", results3)

        # Check if this is an async/creatable select
        fiber_info = await page.evaluate("""() => {
            const el = document.querySelector('#candidate-location');
            if (!el) return null;
            const container = el.closest('[class*="select__container"]') || el.parentElement.parentElement;
            const keys = Object.keys(container || {});
            const fiberKey = keys.find(k => k.startsWith('__reactFiber'));
            if (!fiberKey) return {error: 'no fiber'};

            let fiber = container[fiberKey];
            let depth = 0;
            while (fiber && depth < 30) {
                const type = fiber.type;
                const name = typeof type === 'function' ? (type.name || type.displayName || '') : '';
                if (name.toLowerCase().includes('select') || name.toLowerCase().includes('async') || name.toLowerCase().includes('creatable')) {
                    const props = fiber.memoizedProps || {};
                    return {
                        componentName: name,
                        isAsync: !!props.loadOptions || !!props.defaultOptions || name.includes('Async'),
                        isCreatable: !!props.isCreatable || name.includes('Creatable'),
                        propKeys: Object.keys(props).filter(k => !k.startsWith('_')),
                        inputValue: props.inputValue,
                        placeholder: props.placeholder,
                        noOptionsMessage: typeof props.noOptionsMessage === 'function' ? 'function' : props.noOptionsMessage,
                    };
                }
                fiber = fiber.return;
                depth++;
            }
            return {error: 'no select component found', depth: depth};
        }""")
        print("React fiber:", fiber_info)

        screenshots_dir = "/Users/janedoe/Desktop/job-hunter-agent/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)
        await page.screenshot(path=f"{screenshots_dir}/location_debug.png", full_page=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
