"""Test a REAL Greenhouse form submission end-to-end with React Select handling."""
import asyncio
import os
import sys

async def main():
    from patchright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Find a Greenhouse job - try multiple companies
        import aiohttp
        target_url = None
        target_title = ""
        target_company = ""

        async with aiohttp.ClientSession() as session:
            for company in ["posthog", "linear", "vercel", "figma", "retool", "supabase", "airtable", "anthropic"]:
                try:
                    async with session.get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        data = await resp.json()
                        jobs = data.get("jobs", [])
                        for job in jobs[:5]:
                            url = job.get("absolute_url", "")
                            if "greenhouse.io" in url:
                                target_url = url
                                target_title = job.get("title", "Unknown")
                                target_company = company
                                break
                except Exception:
                    continue
                if target_url:
                    break

        if not target_url:
            print("No suitable job found")
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

        screenshots_dir = "/Users/janedoe/Desktop/job-hunter-agent/screenshots"
        os.makedirs(screenshots_dir, exist_ok=True)

        # ---- Fill regular text fields ----
        user_data = {
            "first_name": "Jane",
            "last_name": "Ahmed",
            "email": "jane.doe@example.com",
            "phone": "5551234567",
        }

        for field_id, value in user_data.items():
            try:
                el = await page.query_selector(f"#{field_id}")
                if el and await el.is_visible():
                    await el.click()
                    await el.fill(value)
                    print(f"  Filled #{field_id}")
                    await asyncio.sleep(0.2)
            except Exception as e:
                print(f"  Failed #{field_id}: {e}")

        # ---- Handle React Select fields ----
        def _id_selector(input_id: str) -> str:
            """Build a CSS selector for an ID, handling IDs starting with digits."""
            if input_id and input_id[0].isdigit():
                return f'[id="{input_id}"]'
            return f"#{input_id}"

        async def fill_react_select(input_id: str, search_terms: list[str]) -> bool:
            """Fill a React Select by trying multiple search terms.
            Falls back to ArrowDown to show all options."""
            try:
                sel = _id_selector(input_id)
                input_el = await page.query_selector(sel)
                if not input_el or not await input_el.is_visible():
                    return False

                # Always add empty-string fallback at end (opens full list, picks first)
                all_terms = list(search_terms) + [""]

                for term in all_terms:
                    # Click and clear
                    await input_el.click()
                    await asyncio.sleep(0.2)
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(0.1)

                    if term:
                        await page.keyboard.type(term, delay=20)
                        await asyncio.sleep(0.6)
                    else:
                        # Open full list
                        await page.keyboard.press("ArrowDown")
                        await asyncio.sleep(0.5)

                    # Check for menu with options
                    option = await page.query_selector('[class*="select__option"]')
                    if option:
                        text = await option.text_content()
                        await option.click()
                        await asyncio.sleep(0.2)
                        label = f"'{term}'" if term else "fallback"
                        print(f"  [{input_id}] Selected: '{text.strip()[:50]}' ({label})")
                        return True

                print(f"  [{input_id}] No options found with any approach")
                return False

            except Exception as e:
                print(f"  [{input_id}] Error: {e}")
                return False

        # Get React Select field info
        react_selects = await page.evaluate("""() => {
            const results = [];
            const controls = document.querySelectorAll('[class*="select__control"]');
            for (const ctrl of controls) {
                const input = ctrl.querySelector('input');
                if (!input) continue;
                let label = '';
                let parent = ctrl.parentElement;
                for (let i = 0; i < 5 && parent; i++) {
                    const labelEl = parent.querySelector('label');
                    if (labelEl) { label = labelEl.textContent.trim(); break; }
                    parent = parent.parentElement;
                }
                const sv = ctrl.querySelector('[class*="select__single-value"]');
                results.push({
                    input_id: input.id || '',
                    label: label,
                    has_value: !!sv,
                    visible: ctrl.offsetParent !== null,
                });
            }
            return results;
        }""")

        print(f"\nFilling {len(react_selects)} React Select fields:")

        # Map labels to search terms (try multiple terms in order of likelihood)
        label_to_terms = {
            "country": ["United States", "US", "America"],
            "relocation": ["Yes", "yes"],
            "in-person": ["Yes", "yes"],
            "ai policy": ["acknowledge", "agree", "I acknowledge", "accept", "I agree"],
            "visa sponsorship": ["No", "no"],
            "require visa": ["No", "no"],
            "will you now": ["No", "no"],
            "future require": ["No", "no"],
            "gender": ["Decline", "decline", "prefer not"],
            "hispanic": ["Decline", "decline", "prefer not", "No"],
            "latino": ["Decline", "decline", "prefer not", "No"],
            "veteran": ["not a protected", "prefer not", "not a veteran"],
            "disability": ["prefer not", "decline", "do not wish"],
            "race": ["Decline", "decline", "prefer not"],
            "ethnicity": ["Decline", "decline", "prefer not"],
        }

        for rs in react_selects:
            if not rs['visible'] or rs['has_value'] or not rs['input_id']:
                continue

            label_lower = rs['label'].lower()
            search_terms = None

            for pattern, terms in label_to_terms.items():
                if pattern in label_lower:
                    search_terms = terms
                    break

            if not search_terms:
                # Default based on id patterns
                iid = rs['input_id'].lower()
                if "country" in iid:
                    search_terms = ["United States"]
                elif "gender" in iid or "hispanic" in iid or "veteran" in iid or "disability" in iid or "race" in iid:
                    search_terms = ["Decline", "prefer not", "not"]
                else:
                    search_terms = ["Yes", "No"]

            await fill_react_select(rs['input_id'], search_terms)

        # ---- Fill textarea fields ----
        textareas = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('textarea').forEach(ta => {
                if (ta.offsetParent === null) return;
                if (ta.name === 'g-recaptcha-response') return;
                if (ta.value.trim()) return;
                const label_el = ta.id ? document.querySelector(`label[for="${ta.id}"]`) : null;
                results.push({ id: ta.id, label: label_el ? label_el.textContent.trim() : '' });
            });
            return results;
        }""")

        for ta in textareas:
            label_lower = ta['label'].lower()
            if "why" in label_lower:
                value = ("I'm deeply passionate about this company's mission and the opportunity to contribute to building "
                        "impactful products. With my experience in AI-native development, full-stack engineering, and "
                        "building LLM-powered systems, I believe I can make meaningful contributions. I'm excited about "
                        "the challenges this role presents and the team I'd be working with.")
            elif "cover" in label_lower:
                value = ("Dear Hiring Manager,\n\nI am excited to apply. With extensive experience in AI development, "
                        "full-stack engineering (React/Next.js, Python/FastAPI), and LLM-powered systems, "
                        "I would be a strong addition to your team.\n\nBest regards,\nJane Doe")
            elif "additional" in label_lower:
                value = "Happy to provide any additional information. Looking forward to hearing from you!"
            else:
                value = "N/A"

            try:
                el = await page.query_selector(f"#{ta['id']}")
                if el:
                    await el.fill(value)
                    print(f"  Filled textarea #{ta['id']}")
            except Exception:
                pass

        # ---- Fill remaining text fields ----
        remaining = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('input[type="text"]').forEach(inp => {
                if (inp.offsetParent === null || inp.value) return;
                if (inp.closest('[class*="select__control"]')) return;
                const label = inp.id ? (document.querySelector(`label[for="${inp.id}"]`)?.textContent?.trim() || '') : '';
                results.push({ id: inp.id, label: label });
            });
            return results;
        }""")

        for field in remaining:
            if not field['id']:
                continue
            label_lower = field['label'].lower()
            value = None
            if "linkedin" in label_lower:
                value = "https://www.linkedin.com/in/janedoe/"
            elif "address" in label_lower or "working" in label_lower or "location" in label_lower:
                value = "Austin, TX"
            elif "github" in label_lower or "website" in label_lower or "portfolio" in label_lower:
                value = "https://github.com/janedoe"
            elif "salary" in label_lower:
                value = "200000"
            elif "url" in label_lower:
                value = "https://www.linkedin.com/in/janedoe/"
            elif "relocating" in label_lower:
                value = "Austin, TX"
            elif field['label']:
                value = "N/A"

            if value:
                try:
                    el = await page.query_selector(f"#{field['id']}")
                    if el:
                        await el.fill(value)
                        print(f"  Filled #{field['id']}")
                except Exception:
                    pass

        # ---- Upload resume ----
        resume_path = "/Users/janedoe/Desktop/Resumes/Jane_Doe_Resume_AI_Native_2026.pdf"
        if os.path.exists(resume_path):
            try:
                fi = await page.query_selector('input[type="file"]')
                if fi:
                    await fi.set_input_files(resume_path)
                    print(f"  Uploaded resume")
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"  Resume upload failed: {e}")

        await page.screenshot(path=f"{screenshots_dir}/02_after_fill.png", full_page=True)

        # ---- Check for unfilled required React Selects ----
        unfilled_selects = await page.evaluate("""() => {
            const unfilled = [];
            document.querySelectorAll('[class*="select__control"]').forEach(ctrl => {
                const sv = ctrl.querySelector('[class*="select__single-value"]');
                if (sv) return;  // Has a value
                let label = '';
                let parent = ctrl.parentElement;
                for (let i = 0; i < 5 && parent; i++) {
                    const labelEl = parent.querySelector('label');
                    if (labelEl) { label = labelEl.textContent.trim(); break; }
                    parent = parent.parentElement;
                }
                if (label.includes('*')) {
                    const input = ctrl.querySelector('input');
                    unfilled.push({ id: input?.id || '', label: label });
                }
            });
            return unfilled;
        }""")

        if unfilled_selects:
            print(f"\nStill unfilled required selects: {len(unfilled_selects)}")
            for f in unfilled_selects:
                print(f"  {f['id']}: {f['label']}")

            # Try one more time with broader search
            for f in unfilled_selects:
                if f['id']:
                    # Get all available options by opening the list
                    await fill_react_select(f['id'], [""])

        # ---- Submit ----
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

        await asyncio.sleep(5)

        # Take screenshot
        await page.screenshot(path=f"{screenshots_dir}/03_after_submit.png", full_page=True)

        # Analyze result
        post_url = page.url
        print(f"\nURL: {pre_url} → {post_url}")

        form_visible = await page.evaluate("""() => {
            const submit = document.querySelector('input[type="submit"], button[type="submit"]');
            return submit ? submit.offsetParent !== null : false;
        }""")

        errors = await page.evaluate("""() => {
            const errs = [];
            document.querySelectorAll('[class*="error"], .field-error').forEach(el => {
                if (el.offsetParent !== null && el.textContent.trim())
                    errs.push(el.textContent.trim().substring(0, 200));
            });
            return [...new Set(errs)];
        }""")

        confirmation = await page.evaluate("""() => {
            const text = document.body.innerText.toLowerCase();
            const phrases = [
                "application has been submitted", "thank you for applying",
                "thanks for applying", "application received",
                "we've received your application", "successfully submitted",
            ];
            for (const p of phrases) {
                if (text.includes(p)) return p;
            }
            return null;
        }""")

        recaptcha_token = await page.evaluate("""() => {
            const el = document.querySelector('[name="g-recaptcha-response"]');
            return el ? el.value.length > 0 : 'no_element';
        }""")

        print(f"Form still visible: {form_visible}")
        print(f"Errors: {errors}")
        print(f"Confirmation: {confirmation}")
        print(f"reCAPTCHA token present: {recaptcha_token}")

        if confirmation and not form_visible:
            print("\n*** SUCCESS: Application submitted! ***")
        elif errors:
            print(f"\n*** FAILED: Validation errors ***")
        elif form_visible and recaptcha_token is False:
            print(f"\n*** BLOCKED: reCAPTCHA required ***")
        elif form_visible:
            print(f"\n*** FAILED: Form still visible ***")
        else:
            print(f"\n*** UNCERTAIN: Check screenshots ***")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
