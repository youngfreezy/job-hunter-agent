"""Apply Selectors -- stores and ranks CSS selectors for job application flows.

Stores selectors for apply buttons, next buttons, submit buttons, etc. per
platform in Postgres. Separate from board_selectors (used for discovery).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import psycopg

from backend.shared.config import get_settings

logger = logging.getLogger(__name__)

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS apply_selectors (
    id SERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    step_type TEXT NOT NULL,
    selector TEXT NOT NULL,
    success_count INT NOT NULL DEFAULT 1,
    fail_count INT NOT NULL DEFAULT 0,
    last_used TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked TIMESTAMPTZ,
    last_check_passed BOOLEAN,
    UNIQUE (platform, step_type, selector)
);
CREATE INDEX IF NOT EXISTS idx_apply_selectors_platform_step
    ON apply_selectors (platform, step_type);
"""

_UPSERT = """\
INSERT INTO apply_selectors (platform, step_type, selector, success_count, last_used)
VALUES (%(platform)s, %(step_type)s, %(selector)s, 1, NOW())
ON CONFLICT (platform, step_type, selector)
DO UPDATE SET
    success_count = apply_selectors.success_count + 1,
    last_used = NOW();
"""

_INCREMENT_FAIL = """\
UPDATE apply_selectors
SET fail_count = fail_count + 1, last_used = NOW()
WHERE platform = %(platform)s AND step_type = %(step_type)s AND selector = %(selector)s;
"""

_GET_TOP = """\
SELECT selector, success_count, fail_count
FROM apply_selectors
WHERE platform = %(platform)s AND step_type = %(step_type)s
ORDER BY (success_count - fail_count) DESC, last_used DESC
LIMIT %(limit)s;
"""

_HEALTH_CHECK = """\
UPDATE apply_selectors
SET last_checked = NOW(), last_check_passed = %(passed)s
WHERE platform = %(platform)s AND step_type = %(step_type)s AND selector = %(selector)s;
"""

_GET_ALL_FOR_PLATFORM = """\
SELECT platform, step_type, selector, success_count, fail_count, last_checked, last_check_passed
FROM apply_selectors
WHERE platform = %(platform)s
ORDER BY step_type, (success_count - fail_count) DESC;
"""

_GET_ALL = """\
SELECT platform, step_type, selector, success_count, fail_count, last_checked, last_check_passed
FROM apply_selectors
ORDER BY platform, step_type, (success_count - fail_count) DESC;
"""


def _connect() -> psycopg.Connection:
    settings = get_settings()
    return psycopg.connect(settings.DATABASE_URL)


async def ensure_table() -> None:
    """Create the apply_selectors table if it doesn't exist."""
    try:
        conn = _connect()
        try:
            conn.execute(_CREATE_TABLE)
            conn.commit()
        finally:
            conn.close()
        logger.info("apply_selectors table ensured")
    except Exception:
        logger.debug("Could not create apply_selectors table", exc_info=True)


def record_success(platform: str, step_type: str, selector: str) -> None:
    try:
        conn = _connect()
        try:
            conn.execute(_UPSERT, {"platform": platform, "step_type": step_type, "selector": selector})
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to record apply selector success", exc_info=True)


def record_failure(platform: str, step_type: str, selector: str) -> None:
    try:
        conn = _connect()
        try:
            conn.execute(_INCREMENT_FAIL, {"platform": platform, "step_type": step_type, "selector": selector})
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to record apply selector failure", exc_info=True)


def get_top_selectors(platform: str, step_type: str, limit: int = 5) -> List[str]:
    """Get top-performing selectors for a platform+step_type, ranked by net success."""
    try:
        conn = _connect()
        try:
            cur = conn.execute(_GET_TOP, {"platform": platform, "step_type": step_type, "limit": limit})
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to get apply selectors for %s/%s", platform, step_type, exc_info=True)
        return []


def record_health_check(platform: str, step_type: str, selector: str, passed: bool) -> None:
    try:
        conn = _connect()
        try:
            conn.execute(_HEALTH_CHECK, {
                "platform": platform, "step_type": step_type,
                "selector": selector, "passed": passed,
            })
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to record health check", exc_info=True)


def get_all_for_platform(platform: str) -> List[Dict]:
    try:
        conn = _connect()
        try:
            cur = conn.execute(_GET_ALL_FOR_PLATFORM, {"platform": platform})
            cols = ["platform", "step_type", "selector", "success_count", "fail_count", "last_checked", "last_check_passed"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to get selectors for %s", platform, exc_info=True)
        return []


def get_all_selectors() -> List[Dict]:
    try:
        conn = _connect()
        try:
            cur = conn.execute(_GET_ALL)
            cols = ["platform", "step_type", "selector", "success_count", "fail_count", "last_checked", "last_check_passed"]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to get all selectors", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Default selectors -- seeded on startup
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Dict[str, List[str]]] = {
    "linkedin": {
        "apply_button": [
            'button.jobs-apply-button',
            'button:has-text("Easy Apply")',
        ],
        "next_button": [
            'button[aria-label="Continue to next step"]',
            'button:has-text("Next")',
        ],
        "submit_button": [
            'button[aria-label="Submit application"]',
            'button:has-text("Submit application")',
        ],
        "close_modal": [
            'button[aria-label="Dismiss"]',
            'button[data-test-modal-close-btn]',
        ],
    },
    "indeed": {
        "apply_button": [
            '#indeedApplyButton',
            'button.jobsearch-IndeedApplyButton',
            'button:has-text("Apply now")',
        ],
        "next_button": [
            'button:has-text("Continue")',
            'button[data-testid="continue-button"]',
        ],
        "submit_button": [
            'button:has-text("Submit your application")',
        ],
    },
    "glassdoor": {
        "apply_button": [
            'button:has-text("Easy Apply")',
            'button:has-text("Apply")',
        ],
        "submit_button": [
            'button:has-text("Submit")',
            'button[type="submit"]',
        ],
    },
    "ziprecruiter": {
        "apply_button": [
            'button:has-text("Apply")',
            'a:has-text("Apply")',
        ],
        "submit_button": [
            'button:has-text("Submit")',
            'button[type="submit"]',
        ],
        "close_modal": [
            'button[aria-label="Close"]',
            'button:has-text("×")',
        ],
    },
    "greenhouse": {
        "apply_button": [
            'a#apply_button',
            'a:has-text("Apply for this job")',
        ],
        "submit_button": [
            'input[type="submit"]',
            'button:has-text("Submit Application")',
        ],
    },
    "lever": {
        "apply_button": [
            'a.postings-btn',
            'a:has-text("Apply for this job")',
        ],
        "submit_button": [
            'button.postings-btn[type="submit"]',
            'button:has-text("Submit application")',
        ],
    },
    "workday": {
        "apply_button": [
            'a[data-automation-id="jobPostingApplyButton"]',
            'button:has-text("Apply")',
        ],
        "next_button": [
            'button[data-automation-id="bottom-navigation-next-button"]',
            'button:has-text("Next")',
        ],
        "submit_button": [
            'button[data-automation-id="submit"]',
            'button:has-text("Submit")',
        ],
    },
}


async def seed_defaults() -> None:
    """Insert default selectors if they don't already exist."""
    try:
        conn = _connect()
        try:
            for platform, steps in _DEFAULTS.items():
                for step_type, selectors in steps.items():
                    for selector in selectors:
                        conn.execute(_UPSERT, {
                            "platform": platform,
                            "step_type": step_type,
                            "selector": selector,
                        })
            conn.commit()
        finally:
            conn.close()
        logger.info("Seeded default apply selectors")
    except Exception:
        logger.debug("Could not seed default apply selectors", exc_info=True)
