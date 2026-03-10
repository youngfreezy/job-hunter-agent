# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Unit tests for Gmail verification code extraction.

Validates that _extract_code correctly handles:
- Real verification codes (4-8 digits)
- False positives like year strings (2026, 2025)
- Emails with dates alongside real codes
- Various code formats (OTP, verification, security)
"""

import pytest

from backend.shared.gmail_client import (
    _extract_code,
    _extract_code_fallback,
    _FALSE_POSITIVE_CODES,
)


class TestExtractCode:
    """Tests for _extract_code (primary extraction)."""

    def test_verification_code_6_digits(self):
        text = "Your verification code is 483921"
        assert _extract_code(text) == "483921"

    def test_verification_code_8_digits(self):
        text = "Your security code is 12345678"
        assert _extract_code(text) == "12345678"

    def test_verification_code_4_digits(self):
        text = "Your verification code is 7391"
        assert _extract_code(text) == "7391"

    def test_otp_code(self):
        text = "Your one-time code: 582714"
        assert _extract_code(text) == "582714"

    def test_code_with_colon(self):
        text = "Code: 948271"
        assert _extract_code(text) == "948271"

    def test_enter_to_verify(self):
        text = "Enter 584920 to verify your email"
        assert _extract_code(text) == "584920"

    def test_code_is_pattern(self):
        text = "Your code is: 391847"
        assert _extract_code(text) == "391847"

    def test_rejects_year_2026(self):
        """The bug: email date '2026' was extracted as a verification code."""
        text = "Date: March 10, 2026\nPlease verify your account."
        assert _extract_code(text) is None

    def test_rejects_year_2025(self):
        text = "Copyright 2025 All rights reserved"
        assert _extract_code(text) is None

    def test_rejects_all_year_false_positives(self):
        for year in _FALSE_POSITIVE_CODES:
            text = f"Date: January 1, {year}. No code here."
            assert _extract_code(text) is None, f"Should not extract {year}"

    def test_real_code_alongside_year(self):
        """Email contains both a year (2026) and a real code (583920)."""
        text = (
            "Date: March 10, 2026\n"
            "Your verification code is 583920\n"
            "This code expires in 10 minutes."
        )
        assert _extract_code(text) == "583920"

    def test_real_6digit_code_alongside_year_no_label(self):
        """Fallback: email has year 2026 and unlabeled 6-digit code."""
        text = (
            "Sent on March 10, 2026\n"
            "Use 847291 to complete sign-in."
        )
        # "code" not in text, but fallback should find 847291
        # Actually "Use X to complete" doesn't match any pattern,
        # but fallback should pick up the 6-digit number
        result = _extract_code(text)
        assert result == "847291"

    def test_security_pin(self):
        text = "Your security pin: 4829"
        assert _extract_code(text) == "4829"

    def test_confirmation_number(self):
        text = "Your confirmation number is 938271"
        assert _extract_code(text) == "938271"

    def test_no_code_in_text(self):
        text = "Thank you for applying. We will be in touch soon."
        assert _extract_code(text) is None

    def test_empty_string(self):
        assert _extract_code("") is None

    def test_code_case_insensitive(self):
        text = "YOUR VERIFICATION CODE IS 482910"
        assert _extract_code(text) == "482910"


class TestExtractCodeFallback:
    """Tests for _extract_code_fallback (last-resort extraction)."""

    def test_prefers_6digit_over_4digit(self):
        text = "Reference 1234 and code 567890"
        assert _extract_code_fallback(text) == "567890"

    def test_skips_year_in_fallback(self):
        text = "Sent in 2026. No other numbers."
        assert _extract_code_fallback(text) is None

    def test_finds_4digit_code_not_year(self):
        text = "Use 8374 to log in"
        assert _extract_code_fallback(text) == "8374"

    def test_skips_all_years(self):
        text = "2024 2025 2026 2027 2028 2029 2030"
        assert _extract_code_fallback(text) is None

    def test_finds_code_among_years(self):
        text = "2026 report, reference 839201"
        assert _extract_code_fallback(text) == "839201"

    def test_empty_string(self):
        assert _extract_code_fallback("") is None
