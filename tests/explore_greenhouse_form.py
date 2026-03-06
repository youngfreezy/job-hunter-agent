"""Explore a real Greenhouse application form to understand submission mechanism."""
import asyncio
import json
import sys

async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Pick a real Greenhouse job page
        # First, find one via API
        import aiohttp
        async with aiohttp.ClientSession() as session:
            # Try anthropic
            async with session.get("https://boards-api.greenhouse.io/v1/boards/anthropic/jobs") as resp:
                data = await resp.json()
                jobs = data.get("jobs", [])
                print(f"Found {len(jobs)} Anthropic jobs")

                # Pick the first one with a URL containing greenhouse
                target_url = None
                for job in jobs[:5]:
                    url = job.get("absolute_url", "")
                    jid = job.get("id", "")
                    title = job.get("title", "")
                    print(f"  - {title}: {url}")
                    if "greenhouse" in url and not target_url:
                        target_url = url

                if not target_url and jobs:
                    target_url = jobs[0].get("absolute_url", "")

        if not target_url:
            print("No job URL found")
            return

        print(f"\nNavigating to: {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Click apply button
        apply_clicked = False
        for sel in ['a#apply_button', 'a:has-text("Apply for this job")', 'button:has-text("Apply")']:
            try:
                el = await page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    await el.click()
                    apply_clicked = True
                    print(f"Clicked apply via: {sel}")
                    break
            except Exception:
                continue

        if not apply_clicked:
            print("Could not find apply button, checking if form is already visible")

        await asyncio.sleep(3)
        await page.wait_for_load_state("domcontentloaded")

        # Now inspect the form
        form_info = await page.evaluate("""() => {
            const info = {
                forms: [],
                react_selects: [],
                hidden_inputs: [],
                all_inputs: [],
                page_url: window.location.href,
            };

            // Get all forms
            document.querySelectorAll('form').forEach(form => {
                info.forms.push({
                    action: form.action,
                    method: form.method,
                    id: form.id,
                    enctype: form.enctype || 'application/x-www-form-urlencoded',
                });
            });

            // Get ALL inputs including hidden
            document.querySelectorAll('input, textarea, select').forEach(el => {
                const label_el = el.id ? document.querySelector(`label[for="${el.id}"]`) : null;
                info.all_inputs.push({
                    tag: el.tagName,
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    value: el.value || '',
                    label: label_el ? label_el.textContent.trim() : '',
                    required: el.required,
                    visible: el.offsetParent !== null,
                    placeholder: el.placeholder || '',
                });
            });

            // Get hidden inputs (CSRF tokens etc)
            document.querySelectorAll('input[type="hidden"]').forEach(el => {
                info.hidden_inputs.push({
                    name: el.name,
                    value: el.value.substring(0, 100),
                });
            });

            // Find React Select containers
            document.querySelectorAll('[class*="select__control"], [class*="Select__control"]').forEach(el => {
                const container = el.closest('[class*="select__container"], [class*="Select__container"]') || el.parentElement;
                const fieldContainer = el.closest('[class*="field"], .field, [data-field]') || el.closest('div');

                // Try to find the label
                let label = '';
                const labelEl = fieldContainer ? fieldContainer.querySelector('label') : null;
                if (labelEl) label = labelEl.textContent.trim();

                // Find any hidden input inside the React Select container
                const hiddenInput = container ? container.querySelector('input[type="hidden"]') : null;
                const textInput = container ? container.querySelector('input:not([type="hidden"])') : null;

                info.react_selects.push({
                    label: label,
                    hidden_input_name: hiddenInput ? hiddenInput.name : null,
                    hidden_input_value: hiddenInput ? hiddenInput.value : null,
                    text_input_name: textInput ? textInput.name : null,
                    text_input_id: textInput ? textInput.id : null,
                    container_class: container ? container.className : '',
                    container_id: container ? container.id : '',
                    html_snippet: el.outerHTML.substring(0, 300),
                });
            });

            return info;
        }""")

        print(f"\nPage URL: {form_info['page_url']}")
        print(f"\nForms ({len(form_info['forms'])}):")
        for f in form_info['forms']:
            print(f"  action={f['action']}, method={f['method']}, id={f['id']}, enctype={f['enctype']}")

        print(f"\nHidden inputs ({len(form_info['hidden_inputs'])}):")
        for h in form_info['hidden_inputs']:
            print(f"  {h['name']}={h['value']}")

        print(f"\nAll inputs ({len(form_info['all_inputs'])}):")
        for inp in form_info['all_inputs']:
            vis = "V" if inp['visible'] else "H"
            print(f"  [{vis}] {inp['tag']} type={inp['type']} name={inp['name']} id={inp['id']} label='{inp['label']}' required={inp['required']} value='{inp['value'][:50]}'")

        print(f"\nReact Select containers ({len(form_info['react_selects'])}):")
        for rs in form_info['react_selects']:
            print(f"  label='{rs['label']}'")
            print(f"    hidden_input: name={rs['hidden_input_name']} value={rs['hidden_input_value']}")
            print(f"    text_input: name={rs['text_input_name']} id={rs['text_input_id']}")
            print(f"    container_id={rs['container_id']}")

        # Try to find React Select options by examining the bundled JS or data attributes
        options_info = await page.evaluate("""() => {
            const results = [];
            // Check if there are any select elements with options
            document.querySelectorAll('select').forEach(sel => {
                const opts = Array.from(sel.options).map(o => ({value: o.value, text: o.text}));
                const label_el = sel.id ? document.querySelector(`label[for="${sel.id}"]`) : null;
                results.push({
                    type: 'native_select',
                    name: sel.name,
                    id: sel.id,
                    label: label_el ? label_el.textContent.trim() : '',
                    options: opts,
                });
            });

            // Check for data attributes on React Select containers
            document.querySelectorAll('[class*="select__container"]').forEach(container => {
                const menu = container.querySelector('[class*="select__menu"]');
                results.push({
                    type: 'react_select_container',
                    has_menu: !!menu,
                    data_attrs: Object.entries(container.dataset || {}),
                    aria_attrs: {
                        role: container.getAttribute('role'),
                        expanded: container.getAttribute('aria-expanded'),
                    },
                });
            });

            return results;
        }""")

        print(f"\nSelect/Options info:")
        for info in options_info:
            print(f"  {json.dumps(info, indent=2)}")

        # Take a screenshot
        screenshot_path = "/Users/fareezahmed/Desktop/job-hunter-agent/screenshots/greenhouse_form_explore.png"
        import os
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"\nScreenshot saved: {screenshot_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
