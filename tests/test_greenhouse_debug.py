"""Debug why Greenhouse form doesn't submit despite no visible errors."""
import asyncio
import os

async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Monitor all network requests
        requests_log = []
        page.on("request", lambda req: requests_log.append({
            "method": req.method,
            "url": req.url[:200],
            "post_data": (req.post_data or "")[:200] if req.method == "POST" else "",
        }))

        responses_log = []
        page.on("response", lambda resp: responses_log.append({
            "url": resp.url[:200],
            "status": resp.status,
        }))

        # Capture console errors
        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text[:200]}"))

        url = "https://job-boards.greenhouse.io/vercel/jobs/5708732004"
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Click apply
        btn = await page.wait_for_selector('button:has-text("Apply")', timeout=5000)
        if btn:
            await btn.click()
            await asyncio.sleep(3)

        def _id_sel(iid):
            return f'[id="{iid}"]' if iid[0].isdigit() else f"#{iid}"

        async def fill_rs(input_id, search_terms):
            sel = _id_sel(input_id)
            el = await page.query_selector(sel)
            if not el or not await el.is_visible():
                return False

            for term in list(search_terms) + [""]:
                await el.click()
                await asyncio.sleep(0.15)
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                if term:
                    await page.keyboard.type(term, delay=15)
                    await asyncio.sleep(0.5)
                else:
                    await page.keyboard.press("ArrowDown")
                    await asyncio.sleep(0.4)

                opt = await page.query_selector('[class*="select__option"]')
                if opt:
                    text = await opt.text_content()
                    await opt.click()
                    await asyncio.sleep(0.2)
                    print(f"  [{input_id}] = '{text.strip()[:50]}'")
                    return True
            print(f"  [{input_id}] FAILED - no options")
            return False

        # Fill basic fields
        for fid, val in [("first_name", "Fareez"), ("last_name", "Ahmed"),
                         ("email", "Fareez.Ahmed@gmail.com"), ("phone", "2026770160")]:
            el = await page.query_selector(f"#{fid}")
            if el: await el.fill(val)

        # Get all React Selects
        rs_fields = await page.evaluate("""() => {
            return [...document.querySelectorAll('[class*="select__control"]')].map(ctrl => {
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
            });
        }""")

        print(f"\nFilling {len(rs_fields)} React Selects:")
        for rs in rs_fields:
            if not rs['visible'] or rs['has_value'] or not rs['id']:
                continue
            label = rs['label'].lower()
            terms = [""]  # Default: just open full list, pick first

            if "country" in label or "country" in rs['id']:
                terms = ["United States"]
            elif "relocation" in label:
                terms = ["Yes"]
            elif "in-person" in label or "office" in label:
                terms = ["Yes"]
            elif "sponsorship" in label or "visa" in label:
                terms = ["No"]
            elif "acknowledge" in label or "privacy" in label or "ai policy" in label or "notice" in label:
                terms = ["acknowledge", "agree", "I acknowledge"]
            elif "reviewed" in label or "double-check" in label or "confirm" in label:
                terms = ["confirm", "reviewed", "I have"]
            elif "authorization" in label or "authorized" in label:
                terms = ["authorized", "citizen"]
            elif "gender" in rs['id'] or "gender" in label:
                terms = ["Decline"]
            elif "hispanic" in rs['id'] or "hispanic" in label:
                terms = ["Decline"]
            elif "veteran" in rs['id'] or "veteran" in label:
                terms = ["not a"]
            elif "disability" in rs['id'] or "disability" in label:
                terms = ["not wish", "prefer"]

            await fill_rs(rs['id'], terms)

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
            el = await page.query_selector(f"#{ta['id']}")
            if el:
                label = ta['label'].lower()
                if "why" in label:
                    await el.fill("I'm passionate about the company's mission and excited to contribute my skills in AI and full-stack engineering.")
                elif "cover" in label:
                    await el.fill("I'd love to bring my experience in building AI-powered applications to your team.")
                else:
                    await el.fill("N/A")

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

        # Check for any unfilled required fields
        unfilled = await page.evaluate("""() => {
            const unfilled = [];
            // Required React Selects without a value
            document.querySelectorAll('[class*="select__control"]').forEach(ctrl => {
                if (ctrl.offsetParent === null) return;
                const sv = ctrl.querySelector('[class*="select__single-value"]');
                if (sv) return;
                let label = '';
                let p = ctrl.parentElement;
                for (let i = 0; i < 5 && p; i++) {
                    const l = p.querySelector('label');
                    if (l) { label = l.textContent.trim(); break; }
                    p = p.parentElement;
                }
                if (label.includes('*')) {
                    unfilled.push({type: 'react_select', label: label, id: ctrl.querySelector('input')?.id});
                }
            });
            // Required inputs without value
            document.querySelectorAll('input[aria-required="true"], input[required]').forEach(inp => {
                if (inp.offsetParent === null || inp.type === 'hidden' || inp.type === 'file') return;
                if (inp.closest('[class*="select__control"]')) return;  // Skip react selects
                if (inp.value) return;
                const label = inp.id ? (document.querySelector(`label[for="${inp.id}"]`)?.textContent?.trim() || '') : '';
                unfilled.push({type: inp.type, label: label, id: inp.id});
            });
            return unfilled;
        }""")

        if unfilled:
            print(f"\nUnfilled required fields ({len(unfilled)}):")
            for f in unfilled:
                print(f"  [{f['type']}] {f['label']} (id={f['id']})")

            # Try to fill remaining required React Selects
            for f in unfilled:
                if f['type'] == 'react_select' and f['id']:
                    await fill_rs(f['id'], [""])
        else:
            print("\nAll required fields filled!")

        screenshots_dir = "/Users/fareezahmed/Desktop/job-hunter-agent/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)
        await page.screenshot(path=f"{screenshots_dir}/debug_before_submit.png", full_page=True)

        # Clear request log before submit
        requests_log.clear()
        responses_log.clear()

        print("\n--- Clicking Submit ---")
        pre_url = page.url

        # Try to click submit
        for sel in ['button:has-text("Submit")', 'input[type="submit"]', 'button[type="submit"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=2000, state="visible")
                if el:
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)

                    # Listen for navigation
                    try:
                        async with page.expect_navigation(timeout=10000):
                            await el.click()
                    except Exception:
                        # Navigation might not happen
                        pass

                    print(f"  Clicked: {sel}")
                    break
            except Exception:
                continue

        await asyncio.sleep(5)

        # Check results
        post_url = page.url
        print(f"\nURL: {pre_url} → {post_url}")
        print(f"URL changed: {pre_url != post_url}")

        print(f"\nPOST requests after submit ({sum(1 for r in requests_log if r['method'] == 'POST')}):")
        for r in requests_log:
            if r['method'] == 'POST':
                print(f"  POST {r['url']}")
                if r['post_data']:
                    print(f"    data: {r['post_data'][:200]}")

        print(f"\nResponses:")
        for r in responses_log:
            if r['status'] != 200 or "application" in r['url'].lower() or "job" in r['url'].lower():
                print(f"  [{r['status']}] {r['url']}")

        print(f"\nConsole messages:")
        for msg in console_msgs[-10:]:
            print(f"  {msg}")

        # Check form state
        form_check = await page.evaluate("""() => {
            const form = document.querySelector('#application-form');
            const submit = document.querySelector('input[type="submit"], button[type="submit"], button:has-text("Submit")');
            const errorEls = document.querySelectorAll('[class*="error"], [class*="Error"], .field-error');
            const errors = [...errorEls].filter(e => e.offsetParent !== null).map(e => e.textContent.trim().substring(0, 100));

            return {
                form_exists: !!form,
                submit_visible: submit ? submit.offsetParent !== null : false,
                errors: [...new Set(errors)],
                page_title: document.title,
                body_text_sample: document.body.innerText.substring(0, 500),
            };
        }""")

        print(f"\nForm state:")
        print(f"  form_exists: {form_check['form_exists']}")
        print(f"  submit_visible: {form_check['submit_visible']}")
        print(f"  errors: {form_check['errors']}")
        print(f"  title: {form_check['page_title']}")

        await page.screenshot(path=f"{screenshots_dir}/debug_after_submit.png", full_page=True)

        # Check reCAPTCHA
        recaptcha = await page.evaluate("""() => {
            const el = document.querySelector('[name="g-recaptcha-response"]');
            return {
                exists: !!el,
                has_token: el ? el.value.length > 0 : false,
                token_len: el ? el.value.length : 0,
            };
        }""")
        print(f"\nreCAPTCHA: {recaptcha}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
