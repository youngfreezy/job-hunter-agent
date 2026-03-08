# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Account Creator -- handles ATS account creation when required for applications.

Some job sites (Workday, iCIMS, Taleo) require account creation before
applying.  This module detects the need for an account and handles the
sign-up flow, pausing for human intervention when email verification is
needed.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, Optional

from backend.shared.config import settings

logger = logging.getLogger(__name__)


class AccountCreationResult:
    """Result of an account creation attempt."""

    def __init__(
        self,
        success: bool,
        needs_email_verification: bool = False,
        account_url: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.needs_email_verification = needs_email_verification
        self.account_url = account_url
        self.error = error


async def detect_account_required(page: Any) -> bool:
    """Check if the current page requires account creation to apply.

    Looks for common patterns: login/register forms, "Create Account" buttons,
    Workday/iCIMS/Taleo sign-in pages.
    """
    indicators = [
        'button:has-text("Create Account")',
        'a:has-text("Create Account")',
        'button:has-text("Sign Up")',
        'a:has-text("Register")',
        'input[name="email"][type="email"]',
        'form[action*="register"]',
        'form[action*="signup"]',
        'div[class*="login-container"]',
        'div[class*="registration"]',
    ]

    for selector in indicators:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                logger.info("Account creation detected via selector: %s", selector)
                return True
        except Exception:
            continue

    return False


async def create_account(
    page: Any,
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
) -> AccountCreationResult:
    """Attempt to create an account on the current ATS page.

    Parameters
    ----------
    page:
        Playwright Page on the registration form.
    email:
        Email address for account creation.
    password:
        Password to use.
    first_name:
        Applicant's first name.
    last_name:
        Applicant's last name.

    Returns
    -------
    AccountCreationResult
    """
    try:
        # Look for email field
        email_field = await page.query_selector(
            'input[type="email"], input[name="email"], '
            'input[name="emailAddress"], input[id*="email"]'
        )
        if email_field:
            await email_field.fill(email)
            await page.wait_for_timeout(random.randint(300, 700))

        # Look for password field
        pw_field = await page.query_selector(
            'input[type="password"], input[name="password"]'
        )
        if pw_field:
            await pw_field.fill(password)
            await page.wait_for_timeout(random.randint(300, 700))

        # Confirm password field (many ATS forms have this)
        confirm_pw = await page.query_selector(
            'input[name="confirmPassword"], input[name="password_confirm"], '
            'input[name="verifyPassword"]'
        )
        if confirm_pw:
            await confirm_pw.fill(password)
            await page.wait_for_timeout(random.randint(200, 500))

        # First name
        if first_name:
            fn_field = await page.query_selector(
                'input[name="firstName"], input[name="first_name"], '
                'input[id*="firstName"]'
            )
            if fn_field:
                await fn_field.fill(first_name)
                await page.wait_for_timeout(random.randint(200, 500))

        # Last name
        if last_name:
            ln_field = await page.query_selector(
                'input[name="lastName"], input[name="last_name"], '
                'input[id*="lastName"]'
            )
            if ln_field:
                await ln_field.fill(last_name)
                await page.wait_for_timeout(random.randint(200, 500))

        # Accept terms checkbox
        terms_cb = await page.query_selector(
            'input[name*="terms"], input[name*="agree"], '
            'input[type="checkbox"][id*="terms"]'
        )
        if terms_cb:
            await terms_cb.check()

        # Submit
        submit_btn = await page.query_selector(
            'button[type="submit"], button:has-text("Create Account"), '
            'button:has-text("Register"), button:has-text("Sign Up"), '
            'input[type="submit"]'
        )
        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(random.randint(2000, 4000))

        # Check if email verification is required
        page_text = await page.inner_text("body")
        verification_phrases = [
            "verify your email",
            "check your email",
            "confirmation email",
            "verification link",
            "activate your account",
        ]
        needs_verification = any(
            phrase in page_text.lower() for phrase in verification_phrases
        )

        if needs_verification:
            logger.info("Account created but needs email verification")
            return AccountCreationResult(
                success=True,
                needs_email_verification=True,
                account_url=page.url,
            )

        logger.info("Account creation appears successful")
        return AccountCreationResult(
            success=True,
            needs_email_verification=False,
            account_url=page.url,
        )

    except Exception as exc:
        logger.exception("Account creation failed")
        return AccountCreationResult(
            success=False,
            error=str(exc),
        )
