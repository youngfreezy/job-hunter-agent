# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Test Greenhouse submission with human-like behavior for better reCAPTCHA scores.

Key improvements:
- Random mouse movements between fields
- Variable typing speeds
- Longer dwell time on page
- Scroll behavior
- Random pauses
"""
import asyncio
import os
import random

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
            "url": resp.url[:200], "status": resp.status,
        }) if resp.request.method == "POST" else None)

        # Find a Greenhouse job
        import aiohttp
        target_url = None
        async with aiohttp.ClientSession() as session:
            for company in ["anthropic", "vercel", "figma", "airtable", "discord"]:
                try:
                    async with session.get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        data = await resp.json()
                        for job in data.get("jobs", [])[:3]:
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

        # Navigate and spend time on the page (builds reCAPTCHA trust)
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # Human-like: scroll down to read the job description
        await page.mouse.move(random.randint(400, 800), random.randint(300, 500))
        await asyncio.sleep(0.5)
        for _ in range(3):
            await page.mouse.wheel(0, random.randint(200, 400))
            await asyncio.sleep(random.uniform(0.5, 1.5))

        # Scroll back up
        await page.mouse.wheel(0, -500)
        await asyncio.sleep(1)

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

        screenshots_dir = os.path.join(os.path.dirname(__file__), "..", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        # --- Human-like form filling helpers ---
        async def human_move_to(x, y):
            """Move mouse to coordinates with slight randomness."""
            cx, cy = x + random.randint(-5, 5), y + random.randint(-5, 5)
            await page.mouse.move(cx, cy, steps=random.randint(3, 8))
            await asyncio.sleep(random.uniform(0.1, 0.3))

        async def human_type(text, el=None):
            """Type with variable delay between keystrokes."""
            if el:
                box = await el.bounding_box()
                if box:
                    await human_move_to(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                await el.click()
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await el.fill("")
            for char in text:
                await page.keyboard.type(char, delay=random.randint(30, 100))
                if random.random() < 0.05:  # Occasional longer pause
                    await asyncio.sleep(random.uniform(0.2, 0.5))

        def _id_sel(iid):
            if iid and iid[0].isdigit():
                return f'[id="{iid}"]'
            return f"#{iid}"

        async def fill_react_select(input_id, search_terms, is_async=False):
            sel = _id_sel(input_id)
            el = await page.query_selector(sel)
            if not el or not await el.is_visible():
                return False
            wait_time = 2.5 if is_async else 0.5

            for term in list(search_terms) + [""]:
                box = await el.bounding_box()
                if box:
                    await human_move_to(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                await el.click()
                await asyncio.sleep(0.2)
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(0.1)

                if term:
                    for char in term:
                        await page.keyboard.type(char, delay=random.randint(40, 80))
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(0.2)

                has_menu = await page.evaluate("""() =>
                    !!document.querySelector('[class*="select__menu"]') ||
                    !!document.querySelector('[role="listbox"]')
                """)
                if not has_menu:
                    await page.keyboard.press("ArrowDown")
                    await asyncio.sleep(0.5)

                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(0.15)
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.3)

                selected = await page.evaluate("""(inputId) => {
                    const sel = inputId.match(/^[0-9]/) ? '[id="' + inputId + '"]' : '#' + CSS.escape(inputId);
                    const input = document.querySelector(sel);
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

        # --- Fill basic text fields with human-like typing ---
        fields = {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@example.com",
            "phone": "5551234567",
        }
        for fid, val in fields.items():
            el = await page.query_selector(f"#{fid}")
            if el and await el.is_visible():
                await human_type(val, el)
                print(f"  Filled #{fid}")
                await asyncio.sleep(random.uniform(0.3, 0.8))

        # Random mouse movement between sections
        await page.mouse.move(random.randint(300, 600), random.randint(400, 600))
        await asyncio.sleep(random.uniform(0.5, 1.0))

        # --- Fill React Selects ---
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
                terms = ["Austin, T", "Austin"]
                is_async = True
            elif "relocation" in label:
                terms = ["Yes"]
            elif "in-person" in label or "office" in label or "comfortable" in label:
                terms = ["Yes"]
            elif "sponsorship" in label or "visa" in label:
                terms = ["No"]
            elif "acknowledge" in label or "privacy" in label or "ai policy" in label or "notice" in label:
                terms = ["acknowledge", "agree", "Yes"]
            elif "reviewed" in label or "confirm" in label or "double-check" in label:
                terms = ["confirm", "reviewed"]
            elif "authorization" in label or "authorized" in label or "permanent work" in label:
                terms = ["Yes", "authorized", "citizen"]
            elif "gender" in rs['id'] or "gender" in label:
                terms = ["Decline"]
            elif "hispanic" in rs['id']:
                terms = ["Decline"]
            elif "veteran" in rs['id']:
                terms = ["not a"]
            elif "disability" in rs['id']:
                terms = ["not wish", "prefer"]

            await fill_react_select(rs['id'], terms, is_async=is_async)
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # --- Fill textareas ---
        textareas = await page.evaluate("""() =>
            [...document.querySelectorAll('textarea')].filter(t =>
                t.offsetParent !== null && t.name !== 'g-recaptcha-response' && !t.value
            ).map(t => ({
                id: t.id,
                label: t.id ? (document.querySelector('label[for=\"' + t.id + '\"]')?.textContent?.trim() || '') : ''
            }))
        """)

        for ta in textareas:
            if not ta['id']:
                continue
            el = await page.query_selector(f"#{ta['id']}")
            if not el:
                continue
            label = ta['label'].lower()
            if "why" in label:
                value = ("I'm deeply passionate about the company's mission and excited to contribute my skills "
                        "in AI-native development and full-stack engineering. With experience building LLM-powered "
                        "systems and agentic workflows, I believe I can make meaningful contributions to the team.")
            elif "cover" in label:
                value = ("Dear Hiring Manager,\n\nI'd love to bring my experience in AI-powered applications "
                        "and full-stack development to your team. My background spans React/Next.js, Python/FastAPI, "
                        "and building LLM-powered systems.\n\nBest regards,\nJane Doe")
            elif "ai" in label and ("experiment" in label or "using" in label):
                value = ("I actively use AI in my daily workflow. My most recent project is an AI-powered job "
                        "application platform that uses LLM agents (Claude) for resume optimization, career coaching, "
                        "and automated application submission. The system uses LangGraph for orchestration, "
                        "browser-use for web automation, and RAG pipelines for intelligent form filling.")
            elif "compensation" in label or "salary" in label:
                value = "200,000"
            elif "additional" in label:
                value = "Happy to provide any additional information. Looking forward to hearing from you!"
            else:
                value = "N/A"
            await human_type(value, el)
            print(f"  Filled textarea #{ta['id']}")
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # --- Fill remaining text inputs ---
        remaining = await page.evaluate("""() =>
            [...document.querySelectorAll('input[type="text"]')].filter(inp =>
                inp.offsetParent !== null && !inp.value && !inp.closest('[class*="select__control"]')
            ).map(inp => ({
                id: inp.id,
                label: inp.id ? (document.querySelector('label[for=\"' + inp.id + '\"]')?.textContent?.trim() || '') : ''
            }))
        """)

        for f in remaining:
            if not f['id']:
                continue
            label = f['label'].lower()
            val = None
            if "linkedin" in label:
                val = "https://www.linkedin.com/in/janedoe/"
            elif "address" in label or "working" in label or "location" in label:
                val = "Austin, TX"
            elif "github" in label or "website" in label:
                val = "https://github.com/janedoe"
            elif "salary" in label or "compensation" in label:
                val = "200000"
            elif "relocat" in label:
                val = "Austin, TX"
            elif f['label']:
                val = "N/A"
            if val:
                el = await page.query_selector(f"#{f['id']}")
                if el:
                    await human_type(val, el)
                    print(f"  Filled #{f['id']}")

        # --- Upload resume ---
        resume_path = "/tmp/test_resume.pdf"
        fi = await page.query_selector('input[type="file"]')
        if fi and os.path.exists(resume_path):
            await fi.set_input_files(resume_path)
            print("  Uploaded resume")
            await asyncio.sleep(2)

        # --- Retry unfilled required fields ---
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

        # Take pre-submit screenshot
        await page.screenshot(path=f"{screenshots_dir}/human_02_filled.png", full_page=True)

        # --- Wait for reCAPTCHA to generate a high-quality token ---
        # Spend more time on the page with human-like behavior
        print("\nDoing human-like activity before submit...")
        await page.mouse.move(random.randint(200, 800), random.randint(300, 600))
        await asyncio.sleep(1)
        await page.mouse.wheel(0, random.randint(100, 300))
        await asyncio.sleep(1)
        await page.mouse.wheel(0, -random.randint(50, 150))
        await asyncio.sleep(2)

        # --- Submit ---
        post_responses.clear()
        print("\nSubmitting...")
        pre_url = page.url

        for sel in ['button:has-text("Submit")', 'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    box = await el.bounding_box()
                    if box:
                        await human_move_to(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    await asyncio.sleep(0.3)
                    await el.click()
                    print(f"  Clicked: {sel}")
                    break
            except Exception:
                continue

        # Wait for response
        await asyncio.sleep(8)

        # Take post-submit screenshot
        await page.screenshot(path=f"{screenshots_dir}/human_03_after_submit.png", full_page=True)

        post_url = page.url
        print(f"\nURL: {pre_url}")
        print(f"  → {post_url}")

        print(f"\nPOST responses:")
        for r in post_responses:
            print(f"  [{r['status']}] {r['url']}")

        # Check result
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

        errors = await page.evaluate("""() =>
            [...new Set([...document.querySelectorAll('[class*="error"], .field-error')]
                .filter(e => e.offsetParent !== null)
                .map(e => e.textContent.trim().substring(0, 100))
                .filter(t => t.length > 0))]
        """)

        form_visible = await page.evaluate("""() => {
            const s = document.querySelector('input[type="submit"], button[type="submit"]');
            return s ? s.offsetParent !== null : false;
        }""")

        has_428 = any(r['status'] == 428 for r in post_responses)
        has_200 = any(r['status'] == 200 and 'jobs' in r['url'] for r in post_responses)

        print(f"\nConfirmation: {confirmation}")
        print(f"Form still visible: {form_visible}")
        print(f"Errors: {errors}")
        print(f"Has 428: {has_428}")
        print(f"Has 200 success: {has_200}")

        if confirmation and not form_visible:
            print("\n*** SUCCESS: Application submitted! ***")
        elif has_200 and not form_visible:
            print("\n*** SUCCESS: 200 response + form gone ***")
        elif errors:
            print(f"\n*** FAILED: Validation errors ***")
        elif has_428:
            print(f"\n*** BLOCKED: reCAPTCHA rejected ***")
        else:
            print(f"\n*** CHECK SCREENSHOT ***")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
