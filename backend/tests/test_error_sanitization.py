# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Tests verifying that internal error details are never leaked to clients."""

import ast
import re


def _read_file(path: str) -> str:
    with open(path) as f:
        return f.read()


class TestHTTPExceptionSanitization:
    """HTTPException detail must never contain str(exc) or f-string with {exc}."""

    def test_sessions_no_raw_exception_in_detail(self):
        """sessions.py HTTPException detail must not expose raw exceptions."""
        content = _read_file("backend/gateway/routes/sessions.py")
        # Find all HTTPException(... detail=...) lines
        # Pattern: detail= followed by str(exc), str(e), f"...{exc}", f"...{e}"
        lines = content.split("\n")
        violations = []
        for i, line in enumerate(lines, 1):
            if "HTTPException" not in line and "detail=" not in line:
                continue
            # Check for str(exc/e/err) in detail
            if re.search(r'detail\s*=\s*str\((exc|e|err)\)', line):
                violations.append(f"Line {i}: {line.strip()}")
            # Check for f-string with {exc} or {e} in detail
            if re.search(r'detail\s*=\s*f"[^"]*\{(exc|e|err)\}', line):
                violations.append(f"Line {i}: {line.strip()}")
        assert not violations, f"Raw exceptions leaked in HTTPException detail:\n" + "\n".join(violations)

    def test_payments_no_raw_exception_in_detail(self):
        """payments.py HTTPException detail must not expose raw exceptions."""
        content = _read_file("backend/gateway/routes/payments.py")
        lines = content.split("\n")
        violations = []
        for i, line in enumerate(lines, 1):
            if "detail=" not in line:
                continue
            if re.search(r'detail\s*=\s*str\((exc|e|err)\)', line):
                violations.append(f"Line {i}: {line.strip()}")
            if re.search(r'detail\s*=\s*f"[^"]*\{(exc|e|err)\}', line):
                violations.append(f"Line {i}: {line.strip()}")
        assert not violations, f"Raw exceptions leaked in HTTPException detail:\n" + "\n".join(violations)


class TestSSEErrorSanitization:
    """SSE error events must not contain str(exc)."""

    def test_no_str_exc_in_emit_calls(self):
        """_emit calls for error/done events must not include str(exc)."""
        content = _read_file("backend/gateway/routes/sessions.py")
        lines = content.split("\n")
        violations = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Look for str(exc) in _emit or event dict context
            if "str(exc)" in stripped and ("_emit" in stripped or '"message"' in stripped or '"error"' in stripped):
                violations.append(f"Line {i}: {stripped}")
        assert not violations, f"Raw exceptions in SSE error events:\n" + "\n".join(violations)


class TestDatabaseURLNotLogged:
    """DATABASE_URL must not appear in log statements."""

    def test_no_database_url_in_logs(self):
        """main.py must not log DATABASE_URL."""
        content = _read_file("backend/gateway/main.py")
        lines = content.split("\n")
        violations = []
        for i, line in enumerate(lines, 1):
            if "logger" in line and "DATABASE_URL" in line:
                violations.append(f"Line {i}: {line.strip()}")
        assert not violations, f"DATABASE_URL found in log statements:\n" + "\n".join(violations)
