# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Test application submission on Lever ATS.
Lever forms are simpler than Greenhouse/Ashby - standard HTML forms with no React Select.
"""
import asyncio
import os

async def main():
    from patchright.async_api import async_playwright
    import aiohttp

    # Lever companies with public job boards
    lever_companies = [
        "netflix", "figma", "stripe", "cloudflare", "databricks",
        "openai", "coinbase", "doordash", "instacart", "robinhood",
        "spotifyab", "discord", "snap", "pinterest", "twitch",
    ]

    target_url = None
    target_title = ""
    target_company = ""

    async with aiohttp.ClientSession() as session:
        for company in lever_companies:
            try:
                url = f"https://api.lever.co/v0/postings/{company}?mode=json"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        print(f"  {company}: {resp.status}")
                        continue
                    jobs = await resp.json()
                    if not isinstance(jobs, list):
                        continue
                    print(f"  {company}: {len(jobs)} jobs")

                    for job in jobs[:20]:
                        title = job.get("text", "")
                        title_lower = title.lower()
                        categories = job.get("categories", {})
                        location = categories.get("location", "")
                        loc_lower = location.lower() if location else ""

                        is_us_remote = any(kw in loc_lower for kw in [
                            "remote", "united states", "us", "austin", "new york",
                            "san francisco", "anywhere", "usa"
                        ])
                        is_engineering = any(kw in title_lower for kw in [
                            "engineer", "developer", "data", "platform", "infra",
                            "ai", "ml", "backend", "frontend", "full-stack", "fullstack"
                        ])

                        if is_engineering and is_us_remote:
                            apply_url = job.get("applyUrl") or job.get("hostedUrl")
                            if apply_url:
                                if "/apply" not in apply_url:
                                    apply_url = apply_url.rstrip("/") + "/apply"
                                target_url = apply_url
                                target_title = title
                                target_company = company
                                break
            except Exception as e:
                print(f"  {company}: {e}")
                continue
            if target_url:
                break

    if not target_url:
        print("No Lever job found")
        return

    print(f"\nTarget: {target_title} at {target_company}")
    print(f"URL: {target_url}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
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

        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        screenshots_dir = "/Users/janedoe/Desktop/job-hunter-agent/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)
        await page.screenshot(path=f"{screenshots_dir}/lever_01_form.png", full_page=True)

        # Analyze form
        form_info = await page.evaluate("""() => {
            const info = {
                inputs: [],
                textareas: [],
                selects: [],
                file_inputs: [],
                captcha: {
                    recaptcha: !!document.querySelector('[name="g-recaptcha-response"], iframe[src*="recaptcha"], script[src*="recaptcha"]'),
                    hcaptcha: !!document.querySelector('[name="h-captcha-response"], iframe[src*="hcaptcha"]'),
                    turnstile: !!document.querySelector('[name="cf-turnstile-response"], script[src*="turnstile"]'),
                },
                buttons: [...document.querySelectorAll('button[type="submit"], input[type="submit"], button.postings-btn')].map(b => b.textContent?.trim()),
            };

            document.querySelectorAll('input:not([type="hidden"]):not([type="submit"])').forEach(inp => {
                if (inp.offsetParent === null) return;
                const label = inp.closest('.application-question')?.querySelector('.application-label')?.textContent?.trim()
                    || document.querySelector('label[for="' + inp.id + '"]')?.textContent?.trim()
                    || inp.placeholder || '';
                info.inputs.push({
                    type: inp.type, name: inp.name, id: inp.id, label: label,
                    required: inp.required || inp.getAttribute('aria-required') === 'true',
                    placeholder: inp.placeholder || '',
                });
            });

            document.querySelectorAll('select').forEach(sel => {
                const label = sel.closest('.application-question')?.querySelector('.application-label')?.textContent?.trim()
                    || document.querySelector('label[for="' + sel.id + '"]')?.textContent?.trim() || '';
                const opts = [...sel.options].map(o => ({value: o.value, text: o.text}));
                info.selects.push({ name: sel.name, id: sel.id, label: label, options: opts });
            });

            document.querySelectorAll('textarea').forEach(ta => {
                if (ta.offsetParent === null || ta.name === 'g-recaptcha-response') return;
                const label = ta.closest('.application-question')?.querySelector('.application-label')?.textContent?.trim()
                    || document.querySelector('label[for="' + ta.id + '"]')?.textContent?.trim() || '';
                info.textareas.push({ name: ta.name, id: ta.id, label: label });
            });

            document.querySelectorAll('input[type="file"]').forEach(fi => {
                const label = fi.closest('.application-question')?.querySelector('.application-label')?.textContent?.trim() || '';
                info.file_inputs.push({ name: fi.name, id: fi.id, label: label });
            });

            return info;
        }""")

        print(f"\nForm analysis:")
        print(f"  CAPTCHA: {form_info['captcha']}")
        print(f"  Inputs: {len(form_info['inputs'])}")
        for inp in form_info['inputs']:
            print(f"    [{inp['type']}] name={inp['name']} id={inp['id']} label='{inp['label'][:50]}' required={inp['required']}")
        print(f"  Selects: {len(form_info['selects'])}")
        for sel in form_info['selects']:
            print(f"    name={sel['name']} id={sel['id']} label='{sel['label'][:50]}' opts={len(sel['options'])}")
        print(f"  Textareas: {len(form_info['textareas'])}")
        for ta in form_info['textareas']:
            print(f"    name={ta['name']} id={ta['id']} label='{ta['label'][:50]}'")
        print(f"  File inputs: {len(form_info['file_inputs'])}")
        print(f"  Buttons: {form_info['buttons']}")

        has_captcha = any(form_info['captcha'].values())
        print(f"\n  CAPTCHA: {'YES - ' + str([k for k,v in form_info['captcha'].items() if v]) if has_captcha else 'NONE'}")

        # Fill the form
        for inp in form_info['inputs']:
            name = inp['name'] or inp['id']
            if not name or inp['type'] in ('file', 'hidden'):
                continue

            label = inp['label'].lower()
            val = None

            if 'name' in label and 'full' in label:
                val = "Jane Doe"
            elif 'first' in label:
                val = "Jane"
            elif 'last' in label:
                val = "Ahmed"
            elif 'email' in label or inp['type'] == 'email':
                val = "jane.doe@example.com"
            elif 'phone' in label or inp['type'] == 'tel':
                val = "5551234567"
            elif 'linkedin' in label:
                val = "https://www.linkedin.com/in/janedoe/"
            elif 'github' in label:
                val = "https://github.com/janedoe"
            elif 'website' in label or 'portfolio' in label or 'url' in label:
                val = "https://github.com/janedoe"
            elif 'locat' in label or 'city' in label or 'address' in label:
                val = "Austin, TX"
            elif 'company' in label or 'org' in label or 'current' in label:
                val = "Independent Consultant"
            elif 'salary' in label or 'compensation' in label:
                val = "200000"
            elif 'hear' in label or 'source' in label or 'referr' in label:
                val = "Job Board"
            elif 'sponsor' in label or 'visa' in label:
                val = "No"
            elif 'authorized' in label or 'eligible' in label:
                val = "Yes"
            elif inp['required']:
                val = "N/A"

            if val:
                try:
                    sel = f'[name="{name}"]' if inp['name'] else f'#{inp["id"]}'
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await el.fill(val)
                        print(f"  Filled {name}={val[:30]}")
                except Exception as e:
                    print(f"  Failed {name}: {e}")

        # Fill selects
        for sel_info in form_info['selects']:
            name = sel_info['name'] or sel_info['id']
            if not name or not sel_info['options']:
                continue
            label = sel_info['label'].lower()
            best = None
            for opt in sel_info['options']:
                text = opt['text'].lower()
                if 'yes' in text and ('authorized' in label or 'eligible' in label or 'relocat' in label):
                    best = opt['value']
                    break
                if 'no' in text and ('sponsor' in label or 'visa' in label):
                    best = opt['value']
                    break
            if not best and len(sel_info['options']) > 1:
                for opt in sel_info['options']:
                    if opt['value'] and opt['text'].strip():
                        best = opt['value']
                        break
            if best:
                try:
                    el = await page.query_selector(f'[name="{name}"]' if sel_info['name'] else f'#{sel_info["id"]}')
                    if el:
                        await el.select_option(value=best)
                        print(f"  Selected {name}={best[:30]}")
                except Exception as e:
                    print(f"  Failed select {name}: {e}")

        # Fill textareas
        for ta in form_info['textareas']:
            name = ta['name'] or ta['id']
            if not name:
                continue
            label = ta['label'].lower()
            if 'cover' in label:
                val = ("I'm excited to apply. With experience in AI-native development, "
                      "full-stack engineering (React/Next.js, Python/FastAPI), and LLM-powered systems, "
                      "I'd be a strong addition to the team.")
            elif 'why' in label:
                val = ("I'm passionate about the company's mission and excited to contribute my AI and "
                      "engineering skills to build impactful products.")
            elif 'additional' in label or 'note' in label:
                val = "Happy to provide additional information."
            else:
                val = "N/A"
            try:
                el = await page.query_selector(f'[name="{name}"]' if ta['name'] else f'#{ta["id"]}')
                if el:
                    await el.fill(val)
                    print(f"  Filled textarea {name}")
            except Exception:
                pass

        # Upload resume
        resume_path = "/Users/janedoe/Desktop/Resumes/Jane_Doe_Resume_AI_Native_2026.pdf"
        if os.path.exists(resume_path):
            try:
                fi = await page.query_selector('input[type="file"]')
                if fi:
                    await fi.set_input_files(resume_path)
                    print("  Uploaded resume")
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"  Resume upload failed: {e}")

        await page.screenshot(path=f"{screenshots_dir}/lever_02_filled.png", full_page=True)

        # Submit
        print("\nSubmitting...")
        post_responses.clear()
        pre_url = page.url

        for sel in ['button.postings-btn', 'button:has-text("Submit application")', 'button:has-text("Submit")', 'button[type="submit"]', 'input[type="submit"]']:
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

        await asyncio.sleep(8)
        post_url = page.url

        await page.screenshot(path=f"{screenshots_dir}/lever_03_after_submit.png", full_page=True)

        print(f"\nURL: {pre_url}")
        print(f"  -> {post_url}")
        print(f"URL changed: {pre_url != post_url}")

        print(f"\nPOST responses:")
        for r in post_responses:
            print(f"  [{r['status']}] {r['url']}")

        # Check result
        page_text = await page.evaluate("() => document.body.innerText.substring(0, 2000)")
        confirmation_phrases = [
            "application has been submitted", "thank you for applying",
            "thanks for applying", "we've received", "application received",
            "submitted successfully", "your application has been",
            "thanks for your interest", "application was submitted",
        ]
        for phrase in confirmation_phrases:
            if phrase in page_text.lower():
                print(f"\n*** SUCCESS: '{phrase}' ***")
                break
        else:
            errors = await page.evaluate("""() =>
                [...document.querySelectorAll('[class*="error"], [role="alert"], .error')]
                    .filter(e => e.offsetParent !== null)
                    .map(e => e.textContent.trim())
                    .filter(t => t.length > 0)
            """)
            if errors:
                print(f"\nErrors: {errors[:5]}")
            else:
                print(f"\nPage text (first 500): {page_text[:500]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
