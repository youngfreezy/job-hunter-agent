"""Find Greenhouse companies that don't have reCAPTCHA on their forms."""
import asyncio
import os

async def main():
    from patchright.async_api import async_playwright
    import aiohttp

    companies = [
        "posthog", "linear", "supabase", "retool", "airtable", "vercel",
        "anthropic", "figma", "discord", "duolingo", "lyft", "affirm",
        "brex", "ramp", "plaid", "gusto", "anduril", "cohere",
        "perplexityai", "mistral", "cerebras", "pinecone",
        "langchain", "notion", "databricks", "verkada",
    ]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()

        no_captcha = []
        has_captcha = []

        async with aiohttp.ClientSession() as session:
            for company in companies:
                try:
                    async with session.get(
                        f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        data = await resp.json()
                        jobs = data.get("jobs", [])
                        if not jobs:
                            print(f"  {company}: no jobs")
                            continue

                        url = None
                        for job in jobs[:3]:
                            u = job.get("absolute_url", "")
                            if "greenhouse.io" in u:
                                url = u
                                break
                        if not url:
                            continue

                        page = await ctx.new_page()
                        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(1)

                        # Click apply
                        for sel in ['button:has-text("Apply")', 'a:has-text("Apply")', 'a#apply_button']:
                            try:
                                el = await page.wait_for_selector(sel, timeout=2000, state="visible")
                                if el:
                                    await el.click()
                                    await asyncio.sleep(2)
                                    break
                            except Exception:
                                continue

                        # Check for captcha
                        captcha = await page.evaluate("""() => {
                            return {
                                recaptcha: !!document.querySelector('[name="g-recaptcha-response"], iframe[src*="recaptcha"], script[src*="recaptcha"]'),
                                hcaptcha: !!document.querySelector('[name="h-captcha-response"], iframe[src*="hcaptcha"], script[src*="hcaptcha"]'),
                                turnstile: !!document.querySelector('[name="cf-turnstile-response"], script[src*="turnstile"]'),
                            };
                        }""")

                        has_any = captcha['recaptcha'] or captcha['hcaptcha'] or captcha['turnstile']

                        if has_any:
                            has_captcha.append(company)
                            captcha_type = []
                            if captcha['recaptcha']: captcha_type.append("reCAPTCHA")
                            if captcha['hcaptcha']: captcha_type.append("hCaptcha")
                            if captcha['turnstile']: captcha_type.append("Turnstile")
                            print(f"  {company}: {', '.join(captcha_type)}")
                        else:
                            no_captcha.append(company)
                            print(f"  {company}: NO CAPTCHA !!!")

                        await page.close()

                except Exception as e:
                    print(f"  {company}: error - {e}")

        await browser.close()

        print(f"\n{'='*50}")
        print(f"No CAPTCHA ({len(no_captcha)}): {', '.join(no_captcha)}")
        print(f"Has CAPTCHA ({len(has_captcha)}): {', '.join(has_captcha)}")

if __name__ == "__main__":
    asyncio.run(main())
