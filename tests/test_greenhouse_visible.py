# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Test Greenhouse submission with headless=False (visible browser).
reCAPTCHA v3 invisible should auto-pass in a real browser window.
"""
import asyncio
import os

async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1920,1080",
            ],
            ignore_default_args=["--enable-automation"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        page = await ctx.new_page()

        # Monitor POST responses
        post_responses = []
        page.on("response", lambda resp: post_responses.append({
            "url": resp.url[:200], "status": resp.status, "method": resp.request.method,
        }) if resp.request.method == "POST" else None)

        # Find a simpler Greenhouse job (try smaller companies first)
        import aiohttp
        target_url = None
        target_title = ""
        target_company = ""

        async with aiohttp.ClientSession() as session:
            for company in ["posthog", "linear", "supabase", "retool", "airtable", "vercel", "anthropic"]:
                try:
                    async with session.get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        data = await resp.json()
                        for job in data.get("jobs", [])[:5]:
                            url = job.get("absolute_url", "")
                            if "greenhouse.io" in url:
                                target_url = url
                                target_title = job.get("title", "")
                                target_company = company
                                break
                except Exception:
                    continue
                if target_url:
                    break

        if not target_url:
            print("No job found")
            return

        print(f"Target: {target_title} at {target_company}")
        print(f"URL: {target_url}")

        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Click apply
        for sel in ['button:has-text("Apply")', 'a:has-text("Apply")', 'a#apply_button']:
            try:
                el = await page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    await el.click()
                    await asyncio.sleep(3)
                    print("Clicked Apply")
                    break
            except Exception:
                continue

        screenshots_dir = "/Users/fareezahmed/Desktop/job-hunter-agent/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)

        def _id_sel(iid):
            if iid and iid[0].isdigit():
                return f'[id="{iid}"]'
            return f"#{iid}"

        async def fill_react_select(input_id, search_terms, is_async=False):
            """Fill React Select using keyboard navigation (works for both
            standard and virtualized/async selects)."""
            sel = _id_sel(input_id)
            el = await page.query_selector(sel)
            if not el or not await el.is_visible():
                return False
            wait_time = 2.5 if is_async else 0.5

            for term in list(search_terms) + [""]:
                await el.click()
                await asyncio.sleep(0.2)
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(0.1)

                if term:
                    await page.keyboard.type(term, delay=30)
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(0.2)

                # Check if menu appeared (either class-based or role-based)
                has_menu = await page.evaluate("""() =>
                    !!document.querySelector('[class*="select__menu"]') ||
                    !!document.querySelector('[role="listbox"]')
                """)
                if not has_menu:
                    await page.keyboard.press("ArrowDown")
                    await asyncio.sleep(0.5)

                # Use keyboard to select first option (works universally)
                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(0.15)
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.3)

                # Verify selection was made
                selected = await page.evaluate("""(inputId) => {
                    const input = document.querySelector(inputId.startsWith('[') ? inputId : '#' + CSS.escape(inputId));
                    if (!input) return null;
                    const ctrl = input.closest('[class*="select__control"]');
                    if (!ctrl) return null;
                    const sv = ctrl.querySelector('[class*="single-value"], [class*="singleValue"]');
                    return sv ? sv.textContent.trim() : null;
                }""", input_id)

                if selected:
                    print(f"  [{input_id}] = '{selected[:50]}'")
                    return True

            print(f"  [{input_id}] FAILED")
            return False

        # Fill basic fields
        for fid, val in [("first_name", "Fareez"), ("last_name", "Ahmed"),
                         ("email", "Fareez.Ahmed@gmail.com"), ("phone", "2026770160")]:
            el = await page.query_selector(f"#{fid}")
            if el and await el.is_visible():
                await el.fill(val)
                print(f"  Filled #{fid}")

        # Fill React Selects
        rs_fields = await page.evaluate("""() =>
            [...document.querySelectorAll('[class*="select__control"]')].map(ctrl => {
                const input = ctrl.querySelector('input');
                let label = '';
                let p = ctrl.parentElement;
                for (let i = 0; i < 5 && p; i++) {
                    const l = p.querySelector('label');
                    if (l) { label = l.textContent.trim(); break; }
                    p = p.parentElement;
                }
                return {
                    id: input?.id || '',
                    label: label,
                    has_value: !!ctrl.querySelector('[class*="select__single-value"]'),
                    visible: ctrl.offsetParent !== null
                };
            })
        """)

        print(f"\nFilling {len(rs_fields)} React Selects:")
        for rs in rs_fields:
            if not rs['visible'] or rs['has_value'] or not rs['id']:
                continue
            label = rs['label'].lower()
            terms = [""]
            is_async = False
            if "country" in label or "country" in rs['id']:
                terms = ["United States"]
            elif "location" in label or "location" in rs['id'] or "city" in label:
                terms = ["Austin, T", "Austin", "New York"]
                is_async = True  # Location autocomplete fetches from API
            elif "relocation" in label: terms = ["Yes"]
            elif "in-person" in label or "office" in label: terms = ["Yes"]
            elif "sponsorship" in label or "visa" in label: terms = ["No"]
            elif "acknowledge" in label or "privacy" in label or "ai policy" in label: terms = ["acknowledge", "agree"]
            elif "reviewed" in label or "confirm" in label or "double-check" in label: terms = ["confirm"]
            elif "authorization" in label or "authorized" in label: terms = ["authorized", "citizen"]
            elif "gender" in rs['id'] or "gender" in label: terms = ["Decline"]
            elif "hispanic" in rs['id']: terms = ["Decline"]
            elif "veteran" in rs['id']: terms = ["not a"]
            elif "disability" in rs['id']: terms = ["not wish", "prefer"]
            await fill_react_select(rs['id'], terms, is_async=is_async)

        # Fill textareas
        textareas = await page.evaluate("""() =>
            [...document.querySelectorAll('textarea')].filter(t =>
                t.offsetParent !== null && t.name !== 'g-recaptcha-response' && !t.value
            ).map(t => ({
                id: t.id,
                label: t.id ? (document.querySelector(`label[for="${t.id}"]`)?.textContent?.trim() || '') : ''
            }))
        """)
        for ta in textareas:
            if not ta['id']: continue
            label = ta['label'].lower()
            if "why" in label:
                value = "I'm deeply passionate about the company's mission and excited to contribute my AI and full-stack engineering skills to build impactful products."
            elif "cover" in label:
                value = "I'd love to bring my experience in AI-powered applications and full-stack development to your team."
            else:
                value = "N/A"
            el = await page.query_selector(f"#{ta['id']}")
            if el:
                await el.fill(value)
                print(f"  Filled textarea #{ta['id']}")

        # Fill remaining text inputs
        remaining = await page.evaluate("""() =>
            [...document.querySelectorAll('input[type="text"]')].filter(inp =>
                inp.offsetParent !== null && !inp.value && !inp.closest('[class*="select__control"]')
            ).map(inp => ({
                id: inp.id,
                label: inp.id ? (document.querySelector(`label[for="${inp.id}"]`)?.textContent?.trim() || '') : ''
            }))
        """)
        for f in remaining:
            if not f['id']: continue
            label = f['label'].lower()
            val = None
            if "linkedin" in label: val = "https://www.linkedin.com/in/fareezahmed/"
            elif "address" in label or "working" in label or "location" in label: val = "Austin, TX"
            elif "github" in label or "website" in label: val = "https://github.com/fareezahmed"
            elif "salary" in label: val = "200000"
            elif "relocat" in label: val = "Austin, TX"
            elif f['label']: val = "N/A"
            if val:
                el = await page.query_selector(f"#{f['id']}")
                if el: await el.fill(val)

        # Upload resume
        resume_path = "/Users/fareezahmed/Desktop/Resumes/Fareez_Ahmed_Resume_AI_Native_2026.pdf"
        fi = await page.query_selector('input[type="file"]')
        if fi and os.path.exists(resume_path):
            await fi.set_input_files(resume_path)
            print("  Uploaded resume")
            await asyncio.sleep(1)

        # Re-fill any remaining unfilled required React Selects
        unfilled = await page.evaluate("""() =>
            [...document.querySelectorAll('[class*="select__control"]')].filter(ctrl =>
                ctrl.offsetParent !== null && !ctrl.querySelector('[class*="select__single-value"]')
            ).map(ctrl => {
                const input = ctrl.querySelector('input');
                let label = '';
                let p = ctrl.parentElement;
                for (let i = 0; i < 5 && p; i++) {
                    const l = p.querySelector('label');
                    if (l) { label = l.textContent.trim(); break; }
                    p = p.parentElement;
                }
                return { id: input?.id || '', label: label };
            }).filter(f => f.label.includes('*'))
        """)
        if unfilled:
            print(f"\nRetrying {len(unfilled)} unfilled required selects:")
            for f in unfilled:
                if f['id']:
                    await fill_react_select(f['id'], [""])

        await page.screenshot(path=f"{screenshots_dir}/visible_02_filled.png", full_page=True)

        # Clear response log before submit
        post_responses.clear()

        # Submit
        print("\nSubmitting...")
        pre_url = page.url
        for sel in ['button:has-text("Submit")', 'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await el.click()
                    print(f"  Clicked: {sel}")
                    break
            except Exception:
                continue

        # Wait longer for submission
        await asyncio.sleep(8)
        post_url = page.url

        await page.screenshot(path=f"{screenshots_dir}/visible_03_after_submit.png", full_page=True)

        print(f"\nURL: {pre_url}")
        print(f"  → {post_url}")
        print(f"URL changed: {pre_url != post_url}")

        print(f"\nPOST responses after submit:")
        for r in post_responses:
            print(f"  [{r['status']}] {r['url']}")

        # Check for confirmation
        confirmation = await page.evaluate("""() => {
            const text = document.body.innerText.toLowerCase();
            const phrases = [
                "application has been submitted", "thank you for applying",
                "thanks for applying", "we've received your application",
                "application received", "successfully submitted",
            ];
            for (const p of phrases) {
                if (text.includes(p)) return p;
            }
            return null;
        }""")

        form_visible = await page.evaluate("""() => {
            const s = document.querySelector('input[type="submit"], button[type="submit"]');
            return s ? s.offsetParent !== null : false;
        }""")

        errors = await page.evaluate("""() =>
            [...new Set([...document.querySelectorAll('[class*="error"], .field-error')]
                .filter(e => e.offsetParent !== null)
                .map(e => e.textContent.trim().substring(0, 100))
                .filter(t => t.length > 0))]
        """)

        print(f"\nConfirmation: {confirmation}")
        print(f"Form still visible: {form_visible}")
        print(f"Errors: {errors}")

        if confirmation and not form_visible:
            print("\n*** SUCCESS: Application submitted! ***")
        elif errors:
            print(f"\n*** FAILED: {errors} ***")
        elif not form_visible and pre_url != post_url:
            print(f"\n*** LIKELY SUCCESS: Form gone + URL changed ***")
        elif form_visible:
            # Check if the 428 happened again
            has_428 = any(r['status'] == 428 for r in post_responses)
            if has_428:
                print(f"\n*** BLOCKED: reCAPTCHA rejected (428) ***")
            else:
                print(f"\n*** UNCERTAIN: Check screenshot ***")
        else:
            print(f"\n*** CHECK SCREENSHOT ***")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
