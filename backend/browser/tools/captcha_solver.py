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
            // hCaptcha FIRST (Lever, Ashby use hCaptcha — must check before reCAPTCHA)
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

            // Also detect hCaptcha by script tag (some sites load it dynamically)
            const hcaptchaScript = document.querySelector('script[src*="hcaptcha.com"]');
            if (hcaptchaScript) {
                // Find the sitekey from any data-sitekey element
                const el = document.querySelector('[data-sitekey]');
                if (el) return { sitekey: el.getAttribute('data-sitekey'), type: 'hcaptcha' };
            }

            // reCAPTCHA v2 — specifically .g-recaptcha class (NOT generic [data-sitekey])
            const recaptchaDiv = document.querySelector('.g-recaptcha[data-sitekey]');
            if (recaptchaDiv) {
                const sitekey = recaptchaDiv.getAttribute('data-sitekey');
                if (sitekey) return { sitekey, type: 'recaptcha_v2' };
            }

            // reCAPTCHA v3 — script src contains sitekey (render param)
            const scripts = document.querySelectorAll('script[src*="recaptcha"]');
            for (const s of scripts) {
                const match = s.src.match(/render=([A-Za-z0-9_-]+)/);
                if (match && match[1] !== 'explicit') {
                    return { sitekey: match[1], type: 'recaptcha_v3' };
                }
            }

            // reCAPTCHA iframe — MOST RELIABLE detection, check FIRST.
            // Enterprise reCAPTCHA is solvable as v3 (not as enterprise type).
            const recaptchaIframes = document.querySelectorAll('iframe[src*="recaptcha"]');
            for (const iframe of recaptchaIframes) {
                const match = iframe.src.match(/[?&]k=([A-Za-z0-9_-]+)/);
                if (match) {
                    // Enterprise and invisible reCAPTCHA both solve as v3
                    const isInvisible = iframe.src.includes('size=invisible') || iframe.src.includes('/enterprise');
                    return { sitekey: match[1], type: isInvisible ? 'recaptcha_v3' : 'recaptcha_v2' };
                }
            }

            // Fallback: check ___grecaptcha_cfg for sitekey (invisible reCAPTCHA without iframe)
            try {
                if (typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients) {
                    // Detect if Enterprise by checking for enterprise property
                    const isEnterprise = !!___grecaptcha_cfg.enterprise;
                    for (const cid in ___grecaptcha_cfg.clients) {
                        const client = ___grecaptcha_cfg.clients[cid];
                        const findKey = (obj, depth) => {
                            if (depth > 5 || !obj) return null;
                            for (const k in obj) {
                                if (k === 'sitekey' || k === 'k') return obj[k];
                                if (typeof obj[k] === 'object') {
                                    const found = findKey(obj[k], depth + 1);
                                    if (found) return found;
                                }
                            }
                            return null;
                        };
                        const key = findKey(client, 0);
                        if (key) return { sitekey: key, type: isEnterprise ? 'recaptcha_enterprise' : 'recaptcha_v2' };
                    }
                }
            } catch(e) {}

            // Fallback: check inline scripts for sitekey references
            if (scripts.length > 0) {
                const allScripts = document.querySelectorAll('script');
                for (const s of allScripts) {
                    if (s.textContent) {
                        const keyMatch = s.textContent.match(/['"]sitekey['"]\s*:\s*['"]([A-Za-z0-9_-]{20,})['"]/);
                        if (keyMatch) return { sitekey: keyMatch[1], type: 'recaptcha_v2' };
                        const renderMatch = s.textContent.match(/grecaptcha\.(?:enterprise\.)?execute\s*\(\s*['"]([A-Za-z0-9_-]{20,})['"]/);
                        if (renderMatch) return { sitekey: renderMatch[1], type: 'recaptcha_v3' };
                    }
                }
            }

            // Fallback: any data-sitekey element — determine type by context
            const genericEl = document.querySelector('[data-sitekey]');
            if (genericEl) {
                const sitekey = genericEl.getAttribute('data-sitekey');
                const isHcaptcha = /^[0-9a-f]{8}-/.test(sitekey);
                return { sitekey, type: isHcaptcha ? 'hcaptcha' : 'recaptcha_v2' };
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
    elif captcha_type == "recaptcha_enterprise":
        # reCAPTCHA Enterprise — same as v2 but with enterprise flag
        params["method"] = "userrecaptcha"
        params["googlekey"] = sitekey
        params["pageurl"] = page_url
        params["enterprise"] = 1
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
        elif captcha_type == "recaptcha_enterprise":
            # reCAPTCHA Enterprise — inject token and force form submission.
            # Enterprise reCAPTCHA intercepts the submit button click, calls
            # grecaptcha.enterprise.execute(), and only submits if it gets a token.
            # We: 1) override execute() to return our token, 2) add hidden field,
            # 3) trigger all callbacks, 4) programmatically submit the form.
            await page.evaluate("""(token) => {
                // 1. Override grecaptcha.enterprise.execute BEFORE submit
                if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {
                    grecaptcha.enterprise.execute = function() {
                        return Promise.resolve(token);
                    };
                    // Also override getResponse
                    grecaptcha.enterprise.getResponse = function() {
                        return token;
                    };
                }

                // 2. Create hidden input with token in ALL forms on the page
                document.querySelectorAll('form').forEach(form => {
                    let input = form.querySelector('input[name="g-recaptcha-response"]');
                    if (!input) {
                        input = document.createElement('input');
                        input.type = 'hidden';
                        input.name = 'g-recaptcha-response';
                        form.appendChild(input);
                    }
                    input.value = token;

                    // Also create textarea version
                    let ta = form.querySelector('#g-recaptcha-response');
                    if (!ta) {
                        ta = document.createElement('textarea');
                        ta.id = 'g-recaptcha-response';
                        ta.name = 'g-recaptcha-response';
                        ta.style.display = 'none';
                        form.appendChild(ta);
                    }
                    ta.value = token;
                });

                // 3. Trigger ALL callbacks in ___grecaptcha_cfg.clients
                try {
                    const clients = ___grecaptcha_cfg.clients;
                    for (const cid in clients) {
                        const walk = (obj, depth) => {
                            if (depth > 6 || !obj) return;
                            for (const key in obj) {
                                if (typeof obj[key] === 'function') {
                                    try { obj[key](token); } catch(e) {}
                                }
                                if (typeof obj[key] === 'object' && obj[key] !== null) {
                                    walk(obj[key], depth + 1);
                                }
                            }
                        };
                        walk(clients[cid], 0);
                    }
                } catch(e) {}
            }""", token)
        else:
            # reCAPTCHA v2/v3
            await page.evaluate("""(token) => {
                // Set response textarea (may be hidden)
                const ta = document.getElementById('g-recaptcha-response');
                if (ta) {
                    ta.style.display = 'block';
                    ta.value = token;
                }

                // Also set any other recaptcha response textareas (multi-widget pages)
                document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
                    el.value = token;
                });

                // Trigger reCAPTCHA callback
                try {
                    const clients = ___grecaptcha_cfg.clients;
                    for (const cid in clients) {
                        const client = clients[cid];
                        const walk = (obj, depth) => {
                            if (depth > 5) return;
                            for (const key in obj) {
                                if (typeof obj[key] === 'function' && key.length < 3) {
                                    try { obj[key](token); } catch(e) {}
                                }
                                if (typeof obj[key] === 'object' && obj[key] !== null) {
                                    walk(obj[key], depth + 1);
                                }
                            }
                        };
                        walk(client, 0);
                    }
                } catch(e) {}

                // Fallback: find and call the callback from data-callback attribute
                const div = document.querySelector('.g-recaptcha[data-callback]');
                if (div) {
                    const cbName = div.getAttribute('data-callback');
                    if (window[cbName]) window[cbName](token);
                }
            }""", token)

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
