# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Test interacting with React Select on Greenhouse forms."""
import asyncio
import os
import sys

async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        url = "https://job-boards.greenhouse.io/anthropic/jobs/5074975008"
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Click apply
        try:
            btn = await page.wait_for_selector('button:has-text("Apply")', timeout=5000)
            if btn:
                await btn.click()
                await asyncio.sleep(3)
                print("Clicked Apply")
        except Exception as e:
            print(f"No apply button: {e}")

        # Try approach 1: Click the React Select control div, then type
        print("\n--- Approach 1: Click control div + type ---")
        try:
            # The country field is a React Select. Its input has id="country"
            # The control div wraps it
            control = await page.query_selector('#country')
            if control:
                # Click the input
                await control.click()
                await asyncio.sleep(0.5)

                # Type to search
                await page.keyboard.type("United States", delay=50)
                await asyncio.sleep(1)

                # Check if menu appeared
                menu = await page.query_selector('[class*="select__menu"]')
                print(f"  Menu appeared after typing: {menu is not None}")

                if menu:
                    # Get options
                    options = await page.locator('[class*="select__option"]').all_text_contents()
                    print(f"  Options: {options[:5]}")

                    # Click first option
                    if options:
                        first_opt = page.locator('[class*="select__option"]').first
                        await first_opt.click()
                        await asyncio.sleep(0.5)

                        # Check if value was set
                        value = await page.evaluate("() => document.querySelector('#country').value")
                        print(f"  Country value after selection: '{value}'")
                else:
                    # Try screenshot to see what happened
                    await page.screenshot(path=os.path.join(os.path.dirname(__file__), "..", "screenshots", "react_select_attempt1.png"), full_page=True)
                    print("  Screenshot saved")

                    # Check what the page shows
                    single_value = await page.evaluate("""() => {
                        const sv = document.querySelector('[class*="select__single-value"]');
                        return sv ? sv.textContent : 'none';
                    }""")
                    print(f"  Single value display: {single_value}")
        except Exception as e:
            print(f"  Error: {e}")

        # Try approach 2: Focus + keyboard events
        print("\n--- Approach 2: Focus + ArrowDown ---")
        try:
            control = await page.query_selector('#question_14523596008')  # relocation question
            if control:
                await control.focus()
                await asyncio.sleep(0.3)

                # Press down arrow to open
                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(0.5)

                menu = await page.query_selector('[class*="select__menu"]')
                print(f"  Menu appeared after ArrowDown: {menu is not None}")

                if menu:
                    options = await page.locator('[class*="select__option"]').all_text_contents()
                    print(f"  Options: {options}")
        except Exception as e:
            print(f"  Error: {e}")

        # Try approach 3: Click the container div (not just the input)
        print("\n--- Approach 3: Click container + space ---")
        try:
            containers = await page.query_selector_all('[class*="select__control"]')
            print(f"  Found {len(containers)} React Select controls")
            if len(containers) > 1:  # Skip country (already tried), use relocation
                container = containers[1]
                await container.click()
                await asyncio.sleep(0.5)

                menu = await page.query_selector('[class*="select__menu"]')
                print(f"  Menu appeared after clicking control: {menu is not None}")

                if not menu:
                    # Try space bar
                    await page.keyboard.press("Space")
                    await asyncio.sleep(0.5)
                    menu = await page.query_selector('[class*="select__menu"]')
                    print(f"  Menu appeared after Space: {menu is not None}")
        except Exception as e:
            print(f"  Error: {e}")

        # Try approach 4: Dispatch mouseDown event on the container
        print("\n--- Approach 4: dispatchEvent mousedown on control ---")
        try:
            result = await page.evaluate("""() => {
                const controls = document.querySelectorAll('[class*="select__control"]');
                const results = [];
                if (controls.length > 2) {
                    const ctrl = controls[2];
                    // Dispatch mousedown
                    ctrl.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));

                    // Wait a tick and check
                    return new Promise(resolve => {
                        setTimeout(() => {
                            const menu = document.querySelector('[class*="select__menu"]');
                            resolve({
                                menu_found: !!menu,
                                menu_html: menu ? menu.innerHTML.substring(0, 500) : null,
                            });
                        }, 500);
                    });
                }
                return {menu_found: false, error: 'not enough controls'};
            }""")
            print(f"  mousedown result: menu_found={result['menu_found']}")
            if result.get('menu_html'):
                print(f"  menu HTML: {result['menu_html'][:200]}")
        except Exception as e:
            print(f"  Error: {e}")

        # Try approach 5: Check if this is a creatable/async select that needs input
        print("\n--- Approach 5: Type into input and check for menu-list ---")
        try:
            # Reset - go to a clean state
            input_el = await page.query_selector('#question_14523587008')  # in-person question
            if input_el:
                await input_el.click()
                await asyncio.sleep(0.3)
                await page.keyboard.type("Y", delay=100)
                await asyncio.sleep(1)

                # Check for any menu/list/options container
                menu_check = await page.evaluate("""() => {
                    const checks = {
                        menu: !!document.querySelector('[class*="select__menu"]'),
                        menuList: !!document.querySelector('[class*="select__menu-list"]'),
                        option: !!document.querySelector('[class*="select__option"]'),
                        listbox: !!document.querySelector('[role="listbox"]'),
                        options_role: document.querySelectorAll('[role="option"]').length,
                    };
                    return checks;
                }""")
                print(f"  Menu check: {menu_check}")
        except Exception as e:
            print(f"  Error: {e}")

        # Try approach 6: Check the actual React component props to find options
        print("\n--- Approach 6: Extract React props from fiber ---")
        try:
            react_info = await page.evaluate("""() => {
                // Find React Select container
                const containers = document.querySelectorAll('[class*="select__container"]');
                const results = [];

                for (const container of [...containers].slice(0, 3)) {
                    // Walk the DOM tree to find React fiber
                    const keys = Object.keys(container);
                    const fiberKey = keys.find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
                    const propsKey = keys.find(k => k.startsWith('__reactProps$'));

                    let info = {
                        has_fiber: !!fiberKey,
                        has_props: !!propsKey,
                    };

                    if (propsKey) {
                        const props = container[propsKey];
                        info.prop_keys = Object.keys(props || {});
                    }

                    if (fiberKey) {
                        let fiber = container[fiberKey];
                        // Walk up to find Select component
                        let depth = 0;
                        while (fiber && depth < 20) {
                            const type = fiber.type;
                            const typeName = typeof type === 'function' ? (type.name || type.displayName) : (typeof type === 'string' ? type : null);
                            if (typeName && (typeName.includes('Select') || typeName.includes('select'))) {
                                // Found it - extract options from props
                                const props = fiber.memoizedProps || fiber.pendingProps || {};
                                info.select_type = typeName;
                                info.options = (props.options || []).slice(0, 10).map(o => ({
                                    value: o.value,
                                    label: o.label,
                                }));
                                break;
                            }
                            fiber = fiber.return;
                            depth++;
                        }
                    }

                    results.push(info);
                }
                return results;
            }""")
            print(f"  React fiber results:")
            for i, info in enumerate(react_info):
                print(f"    [{i}] fiber={info.get('has_fiber')} props={info.get('has_props')} type={info.get('select_type')} options={info.get('options', [])}")
        except Exception as e:
            print(f"  Error: {e}")

        # Take final screenshot
        await page.screenshot(path=os.path.join(os.path.dirname(__file__), "..", "screenshots", "react_select_final.png"), full_page=True)
        print("\nFinal screenshot saved")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
