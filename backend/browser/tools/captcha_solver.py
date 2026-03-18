# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""CAPTCHA solver — detects and solves reCAPTCHA/hCaptcha via 2captcha.

Flow:
1. Extract sitekey from page DOM
2. Send to 2captcha API
3. Poll for solution (15-45s)
4. Inject token into the page
5. Trigger reCAPTCHA callback
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_2CAPTCHA_IN = "https://2captcha.com/in.php"
_2CAPTCHA_RES = "https://2captcha.com/res.php"
_POLL_INTERVAL = 5  # seconds between polls
_MAX_POLL_TIME = 90  # max seconds to wait for solution


async def _extract_sitekey(page) -> Optional[dict]:
    """Extract CAPTCHA sitekey and type from page DOM.

    Returns dict with 'sitekey', 'type' ('recaptcha_v2', 'recaptcha_v3', 'hcaptcha'),
    or None if no CAPTCHA found.
    """
    try:
        result = await page.evaluate("""() => {
            // reCAPTCHA v2 — div with data-sitekey
            const recaptchaDiv = document.querySelector('.g-recaptcha[data-sitekey], [data-sitekey]');
            if (recaptchaDiv) {
                const sitekey = recaptchaDiv.getAttribute('data-sitekey');
                if (sitekey) return { sitekey, type: 'recaptcha_v2' };
            }

            // reCAPTCHA v3 — script src contains sitekey
            const scripts = document.querySelectorAll('script[src*="recaptcha"]');
            for (const s of scripts) {
                const match = s.src.match(/render=([A-Za-z0-9_-]+)/);
                if (match && match[1] !== 'explicit') {
                    return { sitekey: match[1], type: 'recaptcha_v3' };
                }
            }

            // reCAPTCHA iframe — extract sitekey from iframe src
            const iframe = document.querySelector('iframe[src*="recaptcha/api2"], iframe[src*="recaptcha/enterprise"]');
            if (iframe) {
                const match = iframe.src.match(/[?&]k=([A-Za-z0-9_-]+)/);
                if (match) return { sitekey: match[1], type: 'recaptcha_v2' };
            }

            // hCaptcha
            const hcaptchaDiv = document.querySelector('.h-captcha[data-sitekey]');
            if (hcaptchaDiv) {
                const sitekey = hcaptchaDiv.getAttribute('data-sitekey');
                if (sitekey) return { sitekey, type: 'hcaptcha' };
            }

            const hcaptchaIframe = document.querySelector('iframe[src*="hcaptcha.com"]');
            if (hcaptchaIframe) {
                const match = hcaptchaIframe.src.match(/sitekey=([A-Za-z0-9_-]+)/);
                if (match) return { sitekey: match[1], type: 'hcaptcha' };
            }

            return null;
        }""")
        return result
    except Exception as exc:
        logger.debug("Failed to extract CAPTCHA sitekey: %s", exc)
        return None


async def _submit_to_2captcha(
    api_key: str,
    sitekey: str,
    page_url: str,
    captcha_type: str,
) -> Optional[str]:
    """Submit CAPTCHA to 2captcha, return request ID."""
    params = {
        "key": api_key,
        "json": 1,
    }

    if captcha_type == "hcaptcha":
        params["method"] = "hcaptcha"
        params["sitekey"] = sitekey
        params["pageurl"] = page_url
    elif captcha_type == "recaptcha_v3":
        params["method"] = "userrecaptcha"
        params["googlekey"] = sitekey
        params["pageurl"] = page_url
        params["version"] = "v3"
        params["action"] = "submit"
        params["min_score"] = "0.3"
    else:  # recaptcha_v2
        params["method"] = "userrecaptcha"
        params["googlekey"] = sitekey
        params["pageurl"] = page_url

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_2CAPTCHA_IN, data=params)
        data = resp.json()

    if data.get("status") == 1:
        request_id = data.get("request")
        logger.info("2captcha: submitted %s (id=%s)", captcha_type, request_id)
        return request_id

    logger.warning("2captcha submit failed: %s", data)
    return None


async def _poll_solution(api_key: str, request_id: str) -> Optional[str]:
    """Poll 2captcha for solution. Returns token or None."""
    elapsed = 0
    # Initial wait — 2captcha needs time to assign a worker
    await asyncio.sleep(10)
    elapsed += 10

    async with httpx.AsyncClient(timeout=15) as client:
        while elapsed < _MAX_POLL_TIME:
            resp = await client.get(_2CAPTCHA_RES, params={
                "key": api_key,
                "action": "get",
                "id": request_id,
                "json": 1,
            })
            data = resp.json()

            if data.get("status") == 1:
                token = data.get("request", "")
                logger.info("2captcha: solved (id=%s, token=%s...)", request_id, token[:20])
                return token

            if data.get("request") == "CAPCHA_NOT_READY":
                await asyncio.sleep(_POLL_INTERVAL)
                elapsed += _POLL_INTERVAL
                continue

            # Error
            logger.warning("2captcha poll error: %s", data)
            return None

    logger.warning("2captcha: timed out after %ds (id=%s)", elapsed, request_id)
    return None


async def _inject_token(page, token: str, captcha_type: str) -> bool:
    """Inject solved CAPTCHA token into the page."""
    try:
        if captcha_type == "hcaptcha":
            await page.evaluate(f"""(token) => {{
                // Set hCaptcha response textarea
                const ta = document.querySelector('[name="h-captcha-response"], textarea[name="h-captcha-response"]');
                if (ta) ta.value = token;

                // Trigger hCaptcha callback
                if (window.hcaptcha) {{
                    try {{ window.hcaptcha.execute(); }} catch(e) {{}}
                }}
            }}""", token)
        else:
            # reCAPTCHA v2/v3
            await page.evaluate(f"""(token) => {{
                // Set response textarea (may be hidden)
                const ta = document.getElementById('g-recaptcha-response');
                if (ta) {{
                    ta.style.display = 'block';
                    ta.value = token;
                }}

                // Also set any other recaptcha response textareas (multi-widget pages)
                document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {{
                    el.value = token;
                }});

                // Trigger reCAPTCHA callback
                try {{
                    const clients = ___grecaptcha_cfg.clients;
                    for (const cid in clients) {{
                        const client = clients[cid];
                        // Walk the client object tree to find the callback
                        const walk = (obj, depth) => {{
                            if (depth > 5) return;
                            for (const key in obj) {{
                                if (typeof obj[key] === 'function' && key.length < 3) {{
                                    try {{ obj[key](token); }} catch(e) {{}}
                                }}
                                if (typeof obj[key] === 'object' && obj[key] !== null) {{
                                    walk(obj[key], depth + 1);
                                }}
                            }}
                        }};
                        walk(client, 0);
                    }}
                }} catch(e) {{}}

                // Fallback: find and call the callback from data-callback attribute
                const div = document.querySelector('.g-recaptcha[data-callback]');
                if (div) {{
                    const cbName = div.getAttribute('data-callback');
                    if (window[cbName]) window[cbName](token);
                }}
            }}""", token)

        logger.info("CAPTCHA token injected (%s)", captcha_type)
        return True
    except Exception as exc:
        logger.warning("Failed to inject CAPTCHA token: %s", exc)
        return False


async def solve_captcha(page, timeout: int = _MAX_POLL_TIME) -> bool:
    """Detect and solve any CAPTCHA on the current page.

    Returns True if CAPTCHA was solved (or no CAPTCHA present).
    Returns False if solving failed.
    """
    api_key = get_settings().CAPTCHA_API_KEY
    if not api_key:
        logger.debug("CAPTCHA_API_KEY not set — cannot solve CAPTCHAs")
        return False

    # Extract sitekey
    captcha_info = await _extract_sitekey(page)
    if not captcha_info:
        logger.debug("No CAPTCHA detected on page")
        return True  # No CAPTCHA = success

    sitekey = captcha_info["sitekey"]
    captcha_type = captcha_info["type"]
    page_url = page.url
    logger.info("CAPTCHA detected: %s (sitekey=%s...) on %s", captcha_type, sitekey[:10], page_url[:60])

    # Submit to 2captcha
    request_id = await _submit_to_2captcha(api_key, sitekey, page_url, captcha_type)
    if not request_id:
        return False

    # Poll for solution
    token = await _poll_solution(api_key, request_id)
    if not token:
        return False

    # Inject token
    injected = await _inject_token(page, token, captcha_type)
    if not injected:
        return False

    # Small delay for the page to process the token
    await asyncio.sleep(1)
    return True
