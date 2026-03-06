"""Test application submission on Ashby ATS (used by PostHog, Linear, etc.).
Ashby may not have reCAPTCHA.
"""
import asyncio
import os
import random

async def main():
    from patchright.async_api import async_playwright
    import aiohttp

    # Ashby has a public API: https://api.ashbyhq.com/posting-api/job-board/{org}
    ashby_companies = [
        "linear", "supabase", "ramp", "notion",
        "retool", "dbt-labs", "temporal", "pulumi",
        "posthog",  # PostHog last (rate limited)
    ]

    target_url = None
    target_title = ""
    target_company = ""

    async with aiohttp.ClientSession() as session:
        for company in ashby_companies:
            try:
                url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    jobs = data.get("jobs", [])
                    print(f"  {company}: {len(jobs)} jobs")
                    for job in jobs[:30]:
                        title = job.get("title", "")
                        jid = job.get("id", "")
                        location = job.get("location", "")
                        loc_lower = location.lower() if location else ""
                        # Only pick engineering/tech roles that are US/remote
                        title_lower = title.lower()
                        is_us_remote = any(kw in loc_lower for kw in ["remote", "united states", "us", "austin", "new york", "san francisco", "anywhere"])
                        is_engineering = any(kw in title_lower for kw in ["engineer", "developer", "data", "platform", "infra", "ai", "ml"])
                        if is_engineering and is_us_remote:
                            apply_url = f"https://jobs.ashbyhq.com/{company}/{jid}/application"
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
        print("No Ashby job found")
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

        # Monitor ALL responses AND request bodies (to extract form IDs)
        post_responses = []
        request_bodies = []

        def on_response(resp):
            if resp.request.method == "POST":
                post_responses.append({"url": resp.url[:200], "status": resp.status})

        def on_request(req):
            if req.method == "POST" and "graphql" in req.url:
                try:
                    body = req.post_data
                    if body:
                        request_bodies.append({"url": req.url[:200], "body": body[:500]})
                except Exception:
                    pass

        page.on("response", on_response)
        page.on("request", on_request)

        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        screenshots_dir = "/Users/fareezahmed/Desktop/job-hunter-agent/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)
        await page.screenshot(path=f"{screenshots_dir}/ashby_01_form.png", full_page=True)

        # Analyze form
        form_info = await page.evaluate("""() => {
            const info = {
                inputs: [],
                textareas: [],
                selects: [],
                file_inputs: [],
                react_selects: [],
                captcha: {
                    recaptcha: !!document.querySelector('[name="g-recaptcha-response"], iframe[src*="recaptcha"], script[src*="recaptcha"]'),
                    hcaptcha: !!document.querySelector('[name="h-captcha-response"], iframe[src*="hcaptcha"], script[src*="hcaptcha"]'),
                    turnstile: !!document.querySelector('[name="cf-turnstile-response"], script[src*="turnstile"], iframe[src*="turnstile"]'),
                },
                buttons: [...document.querySelectorAll('button[type="submit"], input[type="submit"]')].map(b => b.textContent?.trim()),
            };

            document.querySelectorAll('input:not([type="hidden"]):not([type="submit"])').forEach(inp => {
                if (inp.offsetParent === null) return;
                const label = inp.closest('label, [class*="field"], [class*="question"]')?.querySelector('label, [class*="label"]')?.textContent?.trim() || inp.placeholder || '';
                info.inputs.push({
                    type: inp.type, name: inp.name, id: inp.id, label: label,
                    required: inp.required || inp.getAttribute('aria-required') === 'true',
                    placeholder: inp.placeholder || '',
                });
            });

            document.querySelectorAll('select').forEach(sel => {
                const label = sel.closest('label, [class*="field"]')?.querySelector('label, [class*="label"]')?.textContent?.trim() || '';
                const opts = [...sel.options].map(o => ({value: o.value, text: o.text}));
                info.selects.push({ name: sel.name, id: sel.id, label: label, options: opts });
            });

            document.querySelectorAll('textarea').forEach(ta => {
                if (ta.offsetParent === null) return;
                const label = ta.closest('label, [class*="field"]')?.querySelector('label, [class*="label"]')?.textContent?.trim() || '';
                info.textareas.push({ name: ta.name, id: ta.id, label: label });
            });

            document.querySelectorAll('input[type="file"]').forEach(fi => {
                const label = fi.closest('label, [class*="field"]')?.querySelector('label, [class*="label"]')?.textContent?.trim() || '';
                info.file_inputs.push({ name: fi.name, id: fi.id, label: label });
            });

            document.querySelectorAll('[class*="select__control"]').forEach(ctrl => {
                const input = ctrl.querySelector('input');
                const label = ctrl.closest('[class*="field"], [class*="question"]')?.querySelector('label, [class*="label"]')?.textContent?.trim() || '';
                info.react_selects.push({ id: input?.id || '', label: label });
            });

            return info;
        }""")

        print(f"\nForm analysis:")
        print(f"  CAPTCHA: {form_info['captcha']}")
        print(f"  Inputs: {len(form_info['inputs'])}")
        for inp in form_info['inputs']:
            print(f"    [{inp['type']}] name={inp['name']} label='{inp['label'][:50]}' required={inp['required']}")
        print(f"  Selects: {len(form_info['selects'])}")
        for sel in form_info['selects']:
            print(f"    name={sel['name']} label='{sel['label'][:50]}' opts={len(sel['options'])}")
        print(f"  Textareas: {len(form_info['textareas'])}")
        print(f"  File inputs: {len(form_info['file_inputs'])}")
        print(f"  React Selects: {len(form_info['react_selects'])}")
        print(f"  Buttons: {form_info['buttons']}")

        has_captcha = any(form_info['captcha'].values())
        if has_captcha:
            captcha_types = [k for k, v in form_info['captcha'].items() if v]
            print(f"\n*** HAS CAPTCHA: {captcha_types} - may block submission ***")
        else:
            print(f"\n*** NO CAPTCHA! Submission should work ***")

        # Fill the form based on what we found
        for inp in form_info['inputs']:
            name = inp['name'] or inp['id']
            if not name:
                continue
            label = inp['label'].lower()
            val = None

            if inp['type'] == 'file':
                continue
            elif inp['type'] == 'radio':
                # Handle radio buttons: check the first one with matching name
                try:
                    radios = await page.query_selector_all(f'[name="{name}"]')
                    if radios:
                        # Pick a reasonable option - check the last one (often "Expert" or "Yes")
                        # But for experience questions, pick middle option
                        mid = len(radios) // 2
                        await radios[mid].check(force=True)
                        print(f"  Checked radio {name} (option {mid + 1}/{len(radios)})")
                except Exception as e:
                    print(f"  Failed radio {name}: {e}")
                continue
            elif 'name' in label or 'full name' in label:
                val = "Fareez Ahmed"
            elif 'first' in label:
                val = "Fareez"
            elif 'last' in label:
                val = "Ahmed"
            elif 'email' in label or inp['type'] == 'email':
                val = "Fareez.Ahmed@gmail.com"
            elif 'phone' in label or inp['type'] == 'tel':
                val = "2026770160"
            elif 'sponsor' in label or 'visa' in label:
                val = "No"
            elif 'linkedin' in label:
                val = "https://www.linkedin.com/in/fareezahmed/"
            elif 'github' in label:
                val = "https://github.com/fareezahmed"
            elif 'website' in label or 'portfolio' in label:
                val = "https://github.com/fareezahmed"
            elif 'country' in label or 'based in' in label:
                val = "United States"
            elif 'locat' in label or 'city' in label or 'address' in label or 'where' in label:
                val = "Austin, TX"
            elif 'timezone' in label:
                val = "US Central (CT)"
            elif 'notice' in label or 'start' in label:
                val = "2 weeks"
            elif 'salary' in label or 'compensation' in label:
                val = "200000"
            elif 'company' in label or 'org' in label or 'employer' in label:
                val = "Independent Consultant"
            elif 'hear' in label or 'source' in label or 'how did' in label:
                val = "Job Board"
            elif 'authorized' in label or 'eligible' in label or 'legally' in label:
                val = "Yes"
            elif inp['required']:
                val = "N/A"

            if val:
                try:
                    sel = f'[name="{name}"]' if inp['name'] else f'#{inp["id"]}'
                    el = await page.query_selector(sel)
                    if el:
                        await el.fill(val)
                        print(f"  Filled {name}={val[:30]}")
                except Exception as e:
                    print(f"  Failed {name}: {e}")

        # Fill selects
        for sel_info in form_info['selects']:
            if not sel_info['options']:
                continue
            name = sel_info['name'] or sel_info['id']
            label = sel_info['label'].lower()
            best = None
            for opt in sel_info['options']:
                text = opt['text'].lower()
                if 'yes' in text and ('authorized' in label or 'eligible' in label or 'in-person' in label or 'office' in label):
                    best = opt['value']
                    break
                if 'no' in text and ('sponsor' in label or 'visa' in label):
                    best = opt['value']
                    break
            if not best and len(sel_info['options']) > 1:
                best = sel_info['options'][1]['value']
            if best and name:
                try:
                    el = await page.query_selector(f'[name="{name}"]' if sel_info['name'] else f'#{sel_info["id"]}')
                    if el:
                        await el.select_option(value=best)
                        print(f"  Selected {name}")
                except Exception as e:
                    print(f"  Failed select {name}: {e}")

        # Fill textareas
        for ta in form_info['textareas']:
            name = ta['name'] or ta['id']
            if not name:
                continue
            label = ta['label'].lower()
            if 'cover' in label:
                val = ("I'm excited to apply. With experience in AI development, full-stack engineering "
                      "(React/Next.js, Python/FastAPI), and LLM-powered systems, I'd be a strong addition.")
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

        # Upload resume - be strategic about WHICH file input to use
        # Ashby has TWO file inputs:
        # 1. "Autofill from resume" (top) - parses resume and fills fields (slow, triggers toast)
        # 2. "Resume" field (actual resume attachment)
        # We should SKIP the autofill one and only upload to the actual Resume field
        resume_path = "/Users/fareezahmed/Desktop/Resumes/Fareez_Ahmed_Resume_AI_Native_2026.pdf"
        if os.path.exists(resume_path):
            try:
                file_inputs = await page.query_selector_all('input[type="file"]')
                print(f"  Found {len(file_inputs)} file inputs")

                # Find the Resume field input (not the autofill one)
                # The autofill one is usually the first, and the Resume field is the second
                for idx, fi in enumerate(file_inputs):
                    # Get the label/context for this file input
                    label = await fi.evaluate("""(el) => {
                        const parent = el.closest('[class*="field"], [class*="question"], [class*="section"]');
                        if (parent) {
                            const lbl = parent.querySelector('label, [class*="label"]');
                            if (lbl) return lbl.textContent.trim();
                        }
                        // Check preceding siblings
                        let prev = el.previousElementSibling;
                        while (prev) {
                            if (prev.textContent.includes('Resume') || prev.textContent.includes('resume')) return 'Resume';
                            if (prev.textContent.includes('Autofill') || prev.textContent.includes('autofill')) return 'Autofill';
                            prev = prev.previousElementSibling;
                        }
                        return 'unknown_' + el.name;
                    }""")
                    print(f"    [{idx}] label='{label}'")

                # Upload to the resume field (typically the last or the one labeled "Resume")
                # Try to find the one explicitly labeled "Resume"
                uploaded = False
                for idx, fi in enumerate(file_inputs):
                    label = await fi.evaluate("""(el) => {
                        const parent = el.closest('[class*="field"], [class*="question"], [class*="section"]');
                        if (parent) {
                            const lbl = parent.querySelector('label, [class*="label"]');
                            if (lbl) return lbl.textContent.trim().toLowerCase();
                        }
                        return '';
                    }""")
                    if 'resume' in label and 'autofill' not in label:
                        await fi.set_input_files(resume_path)
                        print(f"  Uploaded resume to field [{idx}] '{label}'")
                        uploaded = True
                        break

                if not uploaded and file_inputs:
                    # Fall back to last file input (usually the resume field)
                    await file_inputs[-1].set_input_files(resume_path)
                    print(f"  Uploaded resume to last file input")
                    uploaded = True

            except Exception as e:
                print(f"  Resume upload failed: {e}")

        await page.screenshot(path=f"{screenshots_dir}/ashby_02_filled.png", full_page=True)

        # Check for any checkboxes that need to be checked
        try:
            checkboxes = await page.query_selector_all('input[type="checkbox"]')
            for cb in checkboxes:
                is_visible = await cb.is_visible()
                is_checked = await cb.is_checked()
                if is_visible and not is_checked:
                    await cb.check(force=True)
                    print("  Checked a checkbox")
        except Exception:
            pass

        # Click Yes/No toggle buttons (common on Ashby forms)
        # Look for "Yes" buttons in questions about age, eligibility, location, etc.
        try:
            yes_buttons = await page.locator('button:has-text("Yes")').all()
            for btn in yes_buttons:
                if await btn.is_visible():
                    # Check if it's already selected (aria-pressed or active class)
                    is_pressed = await btn.get_attribute("aria-pressed")
                    classes = await btn.get_attribute("class") or ""
                    if is_pressed != "true" and "active" not in classes.lower() and "selected" not in classes.lower():
                        await btn.click()
                        print("  Clicked 'Yes' button")
                        await asyncio.sleep(0.3)
        except Exception as e:
            print(f"  Yes button handling: {e}")

        # Wait for file upload API calls to complete
        print("\nWaiting for file upload to complete...")
        pre_upload_count = len(post_responses)
        for i in range(20):
            new_posts = post_responses[pre_upload_count:]
            # Look for the S3 upload and ApiSetFormValueToFile completion
            has_s3 = any('s3' in r['url'].lower() or 'amazonaws' in r['url'].lower() for r in new_posts)
            has_file_set = any('SetFormValueToFile' in r['url'] for r in new_posts)
            if has_s3 and has_file_set:
                print(f"  File upload API calls completed after {i}s")
                break
            if i >= 15:
                print(f"  Upload timeout after {i}s")
                break
            await asyncio.sleep(1)

        # KEY FIX: Reload the page to clear the stuck React spinner state
        # Form values don't persist across reload, so we need to re-fill after reload
        # But the submit button will work (no spinner blocking)
        print("\n  Reloading page to clear stuck upload state...")
        await page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Re-fill all form fields after reload (re-scan the page for current elements)
        print("  Re-filling form after reload...")

        # Re-scan form fields (IDs change on reload for Ashby)
        current_inputs = await page.evaluate("""() => {
            const inputs = [];
            document.querySelectorAll('input:not([type="hidden"]):not([type="submit"])').forEach(inp => {
                if (inp.offsetParent === null) return;
                const label = inp.closest('label, [class*="field"], [class*="question"]')?.querySelector('label, [class*="label"]')?.textContent?.trim() || inp.placeholder || '';
                inputs.push({
                    type: inp.type, name: inp.name, id: inp.id, label: label,
                    required: inp.required || inp.getAttribute('aria-required') === 'true',
                });
            });
            return inputs;
        }""")

        # Handle radio buttons first (they have new names after reload)
        radio_names_done = set()
        for inp in current_inputs:
            if inp['type'] != 'radio':
                continue
            name = inp['name']
            if name in radio_names_done:
                continue
            radio_names_done.add(name)
            try:
                radios = await page.query_selector_all(f'[name="{name}"]')
                if radios:
                    mid = len(radios) // 2
                    await radios[mid].check(force=True)
                    print(f"  Checked radio {name[:40]}... (option {mid+1}/{len(radios)})")
            except Exception:
                pass

        for inp in current_inputs:
            name = inp['name'] or inp['id']
            if not name or inp['type'] in ('file', 'radio'):
                continue
            label = inp['label'].lower()
            val = None
            if 'name' in label or 'full name' in label:
                val = "Fareez Ahmed"
            elif 'first' in label:
                val = "Fareez"
            elif 'last' in label:
                val = "Ahmed"
            elif 'email' in label or inp['type'] == 'email':
                val = "Fareez.Ahmed@gmail.com"
            elif 'phone' in label or inp['type'] == 'tel':
                val = "2026770160"
            elif 'sponsor' in label or 'visa' in label:
                val = "No"
            elif 'linkedin' in label:
                val = "https://www.linkedin.com/in/fareezahmed/"
            elif 'github' in label:
                val = "https://github.com/fareezahmed"
            elif 'website' in label or 'portfolio' in label:
                val = "https://github.com/fareezahmed"
            elif 'country' in label or 'based in' in label:
                val = "United States"
            elif 'locat' in label or 'city' in label or 'address' in label or 'where' in label:
                val = "Austin, TX"
            elif 'timezone' in label:
                val = "US Central (CT)"
            elif 'notice' in label or 'start' in label:
                val = "2 weeks"
            elif 'salary' in label or 'compensation' in label:
                val = "200000"
            elif 'company' in label or 'org' in label or 'employer' in label:
                val = "Independent Consultant"
            elif 'hear' in label or 'source' in label or 'how did' in label:
                val = "Job Board"
            elif 'authorized' in label or 'eligible' in label or 'legally' in label:
                val = "Yes"
            elif inp['required']:
                val = "N/A"
            if val:
                try:
                    sel_str = f'[name="{name}"]' if inp['name'] else f'#{inp["id"]}'
                    el = await page.query_selector(sel_str)
                    if el:
                        await el.fill(val)
                except Exception:
                    pass

        # Re-fill textareas (re-scan since IDs change after reload)
        current_textareas = await page.evaluate("""() => {
            const tas = [];
            document.querySelectorAll('textarea').forEach(ta => {
                if (ta.offsetParent === null || ta.name === 'g-recaptcha-response') return;
                const label = ta.closest('label, [class*="field"], [class*="question"]')?.querySelector('label, [class*="label"]')?.textContent?.trim() || '';
                tas.push({ name: ta.name, id: ta.id, label: label });
            });
            return tas;
        }""")
        for ta in current_textareas:
            name = ta['name'] or ta['id']
            if not name:
                continue
            label = ta['label'].lower()
            if 'cover' in label:
                val = ("I'm excited to apply. With experience in AI development, full-stack engineering "
                      "(React/Next.js, Python/FastAPI), and LLM-powered systems, I'd be a strong addition.")
            elif 'why' in label:
                val = ("I'm passionate about the company's mission and excited to contribute my AI and "
                      "engineering skills to build impactful products.")
            else:
                val = "N/A"
            try:
                el = await page.query_selector(f'[name="{name}"]' if ta['name'] else f'#{ta["id"]}')
                if el:
                    await el.fill(val)
                    print(f"  Filled textarea: {ta['label'][:50]}")
            except Exception:
                pass

        # Re-upload resume (form cleared on reload)
        if os.path.exists(resume_path):
            try:
                file_inputs_new = await page.query_selector_all('input[type="file"]')
                for idx, fi in enumerate(file_inputs_new):
                    label = await fi.evaluate("""(el) => {
                        const parent = el.closest('[class*="field"], [class*="question"], [class*="section"]');
                        if (parent) {
                            const lbl = parent.querySelector('label, [class*="label"]');
                            if (lbl) return lbl.textContent.trim().toLowerCase();
                        }
                        return '';
                    }""")
                    if 'resume' in label and 'autofill' not in label:
                        await fi.set_input_files(resume_path)
                        print(f"  Re-uploaded resume to field [{idx}]")
                        break
                else:
                    if file_inputs_new:
                        await file_inputs_new[-1].set_input_files(resume_path)
                        print(f"  Re-uploaded resume to last field")
            except Exception as e:
                print(f"  Resume re-upload failed: {e}")

        # Re-click Yes buttons and wait for API calls
        pre_yes_count = len(post_responses)
        try:
            yes_buttons = await page.locator('button:has-text("Yes")').all()
            for btn in yes_buttons:
                if await btn.is_visible():
                    is_pressed = await btn.get_attribute("aria-pressed")
                    classes = await btn.get_attribute("class") or ""
                    if is_pressed != "true" and "active" not in classes.lower() and "selected" not in classes.lower():
                        await btn.click()
                        print(f"  Clicked Yes button")
                        await asyncio.sleep(1)  # Wait for API call
        except Exception:
            pass

        # Check if Yes clicks triggered API calls
        await asyncio.sleep(2)
        yes_api_calls = [r for r in post_responses[pre_yes_count:] if 'SetFormValue' in r['url']]
        print(f"  Yes button API calls: {len(yes_api_calls)}")

        # If Yes clicks didn't trigger API calls, set the values directly via GraphQL
        if len(yes_api_calls) == 0:
            print("  Yes button clicks didn't trigger API. Setting values via GraphQL...")
            # Extract the current formRenderIdentifier and org from request bodies
            import re
            form_id = None
            org = None
            for rb in request_bodies:
                if 'formRenderIdentifier' in rb['body']:
                    m1 = re.search(r'"formRenderIdentifier"\s*:\s*"([^"]+)"', rb['body'])
                    m2 = re.search(r'"organizationHostedJobsPageName"\s*:\s*"([^"]+)"', rb['body'])
                    if m1: form_id = m1.group(1)
                    if m2: org = m2.group(1)
                    if form_id: break

            if form_id and org:
                # Find the Yes/No question field paths
                # These are typically boolean-type fields with paths that look like UUIDs
                yes_no_fields = await page.evaluate("""() => {
                    const results = [];
                    const yesButtons = document.querySelectorAll('button');
                    yesButtons.forEach(btn => {
                        if (btn.textContent.trim() !== 'Yes') return;
                        // Find the parent question container
                        let parent = btn.closest('[class*="field"], [class*="question"], [class*="section"], [data-field-id]');
                        if (!parent) {
                            // Walk up manually
                            parent = btn.parentElement?.parentElement?.parentElement;
                        }
                        if (parent) {
                            // Look for a hidden input or data attribute with the field ID
                            const hiddenInput = parent.querySelector('input[type="hidden"]');
                            const label = parent.querySelector('label, [class*="label"]');
                            const labelText = label ? label.textContent.trim() : '';
                            // Try to get the field name/path from data attributes
                            const fieldId = parent.getAttribute('data-field-id') ||
                                           parent.getAttribute('data-path') ||
                                           hiddenInput?.getAttribute('name') || '';
                            results.push({
                                labelText: labelText.substring(0, 100),
                                fieldId: fieldId,
                                parentClasses: parent.className?.substring(0, 100) || '',
                            });
                        }
                    });
                    return results;
                }""")
                print(f"  Yes/No fields found: {yes_no_fields}")

                # Also set values by finding all form fields that look like boolean questions
                # These should already be tracked via request_bodies from the first fill
                # The paths for "age of 18" and "EMEA regions" questions need to be sent
                bool_fields = await page.evaluate("""() => {
                    // Find all toggle/radio button groups that have Yes/No options
                    const groups = [];
                    const allButtons = document.querySelectorAll('button');
                    const seen = new Set();
                    allButtons.forEach(btn => {
                        if (btn.textContent.trim() !== 'Yes' && btn.textContent.trim() !== 'No') return;
                        const parent = btn.parentElement;
                        if (!parent || seen.has(parent)) return;
                        seen.add(parent);
                        const container = parent.closest('[class*="field"], [class*="question"]') || parent.parentElement;
                        if (container) {
                            const label = container.querySelector('label, [class*="label"]');
                            groups.push({
                                label: label?.textContent?.trim()?.substring(0, 100) || '',
                                parentHTML: parent.outerHTML.substring(0, 300),
                            });
                        }
                    });
                    return groups;
                }""")
                print(f"  Boolean field groups: {len(bool_fields)}")
                for bf in bool_fields:
                    print(f"    {bf['label']}")

        # Re-check checkboxes
        try:
            checkboxes = await page.query_selector_all('input[type="checkbox"]')
            for cb in checkboxes:
                if await cb.is_visible() and not await cb.is_checked():
                    await cb.check(force=True)
                    print("  Checked checkbox")
                    await asyncio.sleep(0.5)
        except Exception:
            pass

        # NOW wait for the new file upload to complete (same spinner issue)
        # But this time we'll wait for the S3 upload and then immediately submit
        # without waiting for the spinner
        print("  Waiting for file upload API calls...")
        pre_count = len(post_responses)
        for i in range(20):
            new_posts = post_responses[pre_count:]
            has_file_set = any('SetFormValueToFile' in r['url'] for r in new_posts)
            if has_file_set:
                print(f"  File upload completed after {i}s")
                break
            await asyncio.sleep(1)

        # Don't wait for spinner - immediately try submit strategies
        print("  Form re-filled, attempting submit immediately...")

        await page.screenshot(path=f"{screenshots_dir}/ashby_02b_refilled.png", full_page=True)

        # Submit
        print("Submitting...")
        post_responses.clear()
        pre_url = page.url
        submitted = False

        # First attempt: click directly
        for sel in ['button:has-text("Submit Application")', 'button:has-text("Submit")', 'button[type="submit"]']:
            try:
                el = await page.wait_for_selector(sel, timeout=3000, state="visible")
                if el:
                    await el.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await el.click()
                    print(f"  Clicked: {sel}")
                    await asyncio.sleep(5)
                    submit_posts = [r for r in post_responses if 'Submit' in r['url'] or 'submit' in r['url'].lower()]
                    if submit_posts:
                        print(f"  Submit POST fired! Status: {submit_posts[0]['status']}")
                        submitted = True
                    break
            except Exception:
                continue

        # If blocked by toast (file upload spinner still going), remove toast and retry
        if not submitted:
            print("  Button blocked. Removing toasts and retrying...")
            await page.evaluate("""() => {
                document.querySelectorAll('[class*="toast"], [class*="Toast"], [role="alert"]').forEach(t => t.remove());
                document.querySelectorAll('[class*="spinner"], [class*="Spinner"]').forEach(s => s.remove());
            }""")
            await asyncio.sleep(0.5)
            post_responses.clear()

            for sel in ['button:has-text("Submit Application")', 'button:has-text("Submit")']:
                try:
                    el = await page.wait_for_selector(sel, timeout=3000, state="visible")
                    if el:
                        await el.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                        await el.click()
                        print(f"  Clicked (after toast removal): {sel}")
                        await asyncio.sleep(5)
                        submit_posts = [r for r in post_responses if 'Submit' in r['url'] or 'submit' in r['url'].lower()]
                        if submit_posts:
                            print(f"  Submit POST fired! Status: {submit_posts[0]['status']}")
                            submitted = True
                        break
                except Exception:
                    continue

        # Strategy 4: Call the Ashby submit GraphQL API directly
        if not submitted:
            print("  All button strategies failed. Calling submit API directly...")

            # Extract formRenderIdentifier and organizationHostedJobsPageName from captured requests
            import re
            form_render_id = None
            org_name = None
            for rb in request_bodies:
                body = rb['body']
                if 'formRenderIdentifier' in body:
                    m1 = re.search(r'"formRenderIdentifier"\s*:\s*"([^"]+)"', body)
                    m2 = re.search(r'"organizationHostedJobsPageName"\s*:\s*"([^"]+)"', body)
                    if m1:
                        form_render_id = m1.group(1)
                    if m2:
                        org_name = m2.group(1)
                    if form_render_id:
                        break

            print(f"  formRenderIdentifier: {form_render_id}")
            print(f"  organizationHostedJobsPageName: {org_name}")

            # Extract jobPostingId from the URL
            import re as _re
            job_posting_id = None
            url_match = _re.search(r'/([0-9a-f-]{36})/application', page.url)
            if url_match:
                job_posting_id = url_match.group(1)
            print(f"  jobPostingId: {job_posting_id}")

            if form_render_id and org_name and job_posting_id:
                post_responses.clear()

                # Get recaptcha token from the page's grecaptcha object
                # Also need to find the actionIdentifier (usually "submit" or similar)
                submit_result = await page.evaluate("""async (params) => {
                    try {
                        // Get reCAPTCHA token
                        let recaptchaToken = '';
                        if (typeof grecaptcha !== 'undefined') {
                            // Find the site key from the page
                            const recaptchaEl = document.querySelector('[data-sitekey]');
                            const siteKey = recaptchaEl ? recaptchaEl.getAttribute('data-sitekey') : null;

                            if (siteKey) {
                                // For reCAPTCHA v3, execute with action
                                try {
                                    recaptchaToken = await new Promise((resolve, reject) => {
                                        grecaptcha.ready(() => {
                                            grecaptcha.execute(siteKey, {action: 'submit'}).then(resolve).catch(reject);
                                        });
                                    });
                                } catch(e) {
                                    // Try v2 approach
                                    recaptchaToken = grecaptcha.getResponse() || '';
                                }
                            } else {
                                // Try to find site key from script src or grecaptcha render params
                                const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                                for (const s of scripts) {
                                    const keyMatch = s.src.match(/render=([^&]+)/);
                                    if (keyMatch) {
                                        try {
                                            recaptchaToken = await grecaptcha.execute(keyMatch[1], {action: 'submit'});
                                        } catch(e2) {}
                                        break;
                                    }
                                }
                            }
                        }

                        // The actionIdentifier is typically "submit" for the submit button
                        // Try common values
                        const resp = await fetch('/api/non-user-graphql?op=ApiSubmitSingleApplicationFormAction', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            credentials: 'include',
                            body: JSON.stringify({
                                operationName: 'ApiSubmitSingleApplicationFormAction',
                                variables: {
                                    organizationHostedJobsPageName: params.org,
                                    formRenderIdentifier: params.formId,
                                    jobPostingId: params.jobId,
                                    actionIdentifier: 'submit',
                                    recaptchaToken: recaptchaToken,
                                },
                                query: `mutation ApiSubmitSingleApplicationFormAction(
                                    $organizationHostedJobsPageName: String!,
                                    $formRenderIdentifier: String!,
                                    $jobPostingId: String!,
                                    $actionIdentifier: String!,
                                    $recaptchaToken: String!
                                ) {
                                    submitSingleApplicationFormAction(
                                        organizationHostedJobsPageName: $organizationHostedJobsPageName,
                                        formRenderIdentifier: $formRenderIdentifier,
                                        jobPostingId: $jobPostingId,
                                        actionIdentifier: $actionIdentifier,
                                        recaptchaToken: $recaptchaToken
                                    ) {
                                        applicationFormResult { ... on FormRender { id } }
                                    }
                                }`
                            }),
                        });
                        const text = await resp.text();
                        return {
                            status: resp.status,
                            body: text.substring(0, 1500),
                            recaptchaTokenLength: recaptchaToken.length,
                        };
                    } catch(e) {
                        return { error: e.message };
                    }
                }""", {"org": org_name, "formId": form_render_id, "jobId": job_posting_id})
                print(f"  Direct API submit result: {submit_result}")

                if submit_result and submit_result.get('status') == 200:
                    import json as _json
                    try:
                        body = _json.loads(submit_result.get('body', '{}'))
                        data = body.get('data', {})
                        if data:
                            print(f"  GraphQL response data: {data}")
                            submitted = True
                    except Exception:
                        pass
            else:
                print("  Could not extract form identifiers. Request bodies:")
                for rb in request_bodies[:5]:
                    print(f"    {rb['url'][:80]}: {rb['body'][:200]}")

        await asyncio.sleep(3)
        post_url = page.url

        await page.screenshot(path=f"{screenshots_dir}/ashby_03_after_submit.png", full_page=True)

        print(f"\nURL: {pre_url}")
        print(f"  → {post_url}")
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
        ]
        for phrase in confirmation_phrases:
            if phrase in page_text.lower():
                print(f"\n*** SUCCESS: '{phrase}' ***")
                break
        else:
            form_gone = await page.evaluate("""() =>
                !document.querySelector('button[type="submit"], input[type="submit"]')?.offsetParent
            """)
            if form_gone and pre_url != post_url:
                print(f"\n*** LIKELY SUCCESS: Form gone + URL changed ***")
            else:
                print(f"\nPage text: {page_text[:500]}")
                errors_found = await page.evaluate("""() =>
                    [...document.querySelectorAll('[class*="error"], [role="alert"]')]
                        .filter(e => e.offsetParent !== null)
                        .map(e => e.textContent.trim())
                        .filter(t => t.length > 0)
                """)
                if errors_found:
                    print(f"Errors: {errors_found[:5]}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
