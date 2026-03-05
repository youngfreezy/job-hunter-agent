"""Anti-detection utilities for Playwright browser automation.

Provides stealth configurations, randomised browser fingerprints, and runtime
JavaScript patches that make automated browsers harder for bot-detection
systems to identify.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Tuple

# ---------------------------------------------------------------------------
# User-Agent pool -- realistic, recent desktop browsers
# ---------------------------------------------------------------------------

_USER_AGENTS: list[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# ---------------------------------------------------------------------------
# Viewport pool -- common desktop resolutions
# ---------------------------------------------------------------------------

_VIEWPORTS: list[Dict[str, int]] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
    {"width": 2560, "height": 1440},
    {"width": 1680, "height": 1050},
    {"width": 1280, "height": 800},
    {"width": 1360, "height": 768},
]

# ---------------------------------------------------------------------------
# Locale / timezone pairs
# ---------------------------------------------------------------------------

_LOCALE_TZ: list[Tuple[str, str]] = [
    ("en-US", "America/New_York"),
    ("en-US", "America/Chicago"),
    ("en-US", "America/Denver"),
    ("en-US", "America/Los_Angeles"),
    ("en-US", "America/Phoenix"),
    ("en-GB", "Europe/London"),
    ("en-CA", "America/Toronto"),
    ("en-AU", "Australia/Sydney"),
]

# ---------------------------------------------------------------------------
# Stealth JavaScript -- injected into every page
# ---------------------------------------------------------------------------

_STEALTH_JS = """
// ---- Remove navigator.webdriver flag ----
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// ---- Spoof navigator.plugins (Chrome-like) ----
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ],
});

// ---- Spoof navigator.languages ----
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// ---- Fix chrome.runtime (present in real Chrome) ----
if (!window.chrome) {
    window.chrome = {};
}
if (!window.chrome.runtime) {
    window.chrome.runtime = {
        connect: function() {},
        sendMessage: function() {},
    };
}

// ---- Spoof permissions query ----
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// ---- Mask iframe contentWindow detection ----
const iframeProto = HTMLIFrameElement.prototype;
const originalContentWindow = Object.getOwnPropertyDescriptor(
    iframeProto,
    'contentWindow'
);
if (originalContentWindow) {
    Object.defineProperty(iframeProto, 'contentWindow', {
        get: function () {
            const win = originalContentWindow.get.call(this);
            if (win) {
                // Prevent detection via cross-origin iframe checks
                try { win.chrome; } catch(e) {}
            }
            return win;
        },
    });
}

// ---- WebGL vendor / renderer spoofing ----
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (param) {
    // UNMASKED_VENDOR_WEBGL
    if (param === 37445) return 'Intel Inc.';
    // UNMASKED_RENDERER_WEBGL
    if (param === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, param);
};

// ---- Canvas fingerprint noise ----
const toBlob = HTMLCanvasElement.prototype.toBlob;
const toDataURL = HTMLCanvasElement.prototype.toDataURL;

HTMLCanvasElement.prototype.toBlob = function () {
    const ctx = this.getContext('2d');
    if (ctx) {
        const style = ctx.fillStyle;
        ctx.fillStyle = 'rgba(0,0,1,0.01)';
        ctx.fillRect(0, 0, 1, 1);
        ctx.fillStyle = style;
    }
    return toBlob.apply(this, arguments);
};

HTMLCanvasElement.prototype.toDataURL = function () {
    const ctx = this.getContext('2d');
    if (ctx) {
        const style = ctx.fillStyle;
        ctx.fillStyle = 'rgba(0,0,1,0.01)';
        ctx.fillRect(0, 0, 1, 1);
        ctx.fillStyle = style;
    }
    return toDataURL.apply(this, arguments);
};
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_random_user_agent() -> str:
    """Return a randomly selected realistic desktop user agent string."""
    return random.choice(_USER_AGENTS)


def get_random_viewport() -> Dict[str, int]:
    """Return a randomly selected common desktop viewport size."""
    return dict(random.choice(_VIEWPORTS))  # shallow copy


def get_random_locale_timezone() -> Tuple[str, str]:
    """Return a random (locale, timezone_id) pair."""
    return random.choice(_LOCALE_TZ)


def get_stealth_config() -> Dict[str, Any]:
    """Return a full dict of browser launch args tuned for stealth.

    These arguments are passed to ``browser.launch()`` (Chromium).
    """
    return {
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--window-size=1920,1080",
        ],
        "ignore_default_args": [
            "--enable-automation",
        ],
        "headless": True,
    }


async def apply_stealth(page: Any) -> None:
    """Apply stealth settings to a page.

    Patchright already includes anti-detection patches at the browser level,
    so we skip ``add_init_script`` which causes ``ERR_NAME_NOT_RESOLVED``
    in patchright's Chromium build.  The stealth JS is kept in this module
    for reference if we ever switch back to vanilla playwright.
    """
    # Patchright handles webdriver, plugins, etc. at the browser level.
    # Calling page.add_init_script() breaks DNS resolution in patchright.
    pass
