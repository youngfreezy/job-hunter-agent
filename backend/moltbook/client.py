# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Async HTTP client for the Moltbook social API.

Handles authentication, rate-limit tracking, and the math-verification
challenge flow that Moltbook requires before certain write operations.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.moltbook.com/api/v1"

# Rate limits (conservative — stay well under Moltbook's actual limits)
POST_COOLDOWN_SECONDS = 30 * 60  # 1 post per 30 minutes
MAX_COMMENTS_PER_DAY = 50
MAX_WRITES_PER_60S = 30


# ---------------------------------------------------------------------------
# Rate-limit tracker
# ---------------------------------------------------------------------------


@dataclass
class _RateLimiter:
    """In-process rate-limit tracker for Moltbook API calls."""

    last_post_ts: float = 0.0
    comment_timestamps_today: List[float] = field(default_factory=list)
    write_timestamps: List[float] = field(default_factory=list)

    # --- helpers ---

    def _prune_old_writes(self) -> None:
        cutoff = time.time() - 60
        self.write_timestamps = [t for t in self.write_timestamps if t > cutoff]

    def _prune_old_comments(self) -> None:
        """Keep only today's comments (rolling 24h window)."""
        cutoff = time.time() - 86400
        self.comment_timestamps_today = [
            t for t in self.comment_timestamps_today if t > cutoff
        ]

    # --- checks ---

    def can_post(self) -> bool:
        self._prune_old_writes()
        now = time.time()
        if now - self.last_post_ts < POST_COOLDOWN_SECONDS:
            return False
        if len(self.write_timestamps) >= MAX_WRITES_PER_60S:
            return False
        return True

    def can_comment(self) -> bool:
        self._prune_old_writes()
        self._prune_old_comments()
        if len(self.comment_timestamps_today) >= MAX_COMMENTS_PER_DAY:
            return False
        if len(self.write_timestamps) >= MAX_WRITES_PER_60S:
            return False
        return True

    def can_write(self) -> bool:
        self._prune_old_writes()
        return len(self.write_timestamps) < MAX_WRITES_PER_60S

    # --- record ---

    def record_post(self) -> None:
        now = time.time()
        self.last_post_ts = now
        self.write_timestamps.append(now)

    def record_comment(self) -> None:
        now = time.time()
        self.comment_timestamps_today.append(now)
        self.write_timestamps.append(now)

    def record_write(self) -> None:
        self.write_timestamps.append(time.time())

    # --- info ---

    def seconds_until_next_post(self) -> float:
        elapsed = time.time() - self.last_post_ts
        remaining = POST_COOLDOWN_SECONDS - elapsed
        return max(0.0, remaining)

    def comments_remaining_today(self) -> int:
        self._prune_old_comments()
        return max(0, MAX_COMMENTS_PER_DAY - len(self.comment_timestamps_today))


# Module-level singleton
_rate_limiter = _RateLimiter()


def get_rate_limiter() -> _RateLimiter:
    return _rate_limiter


# ---------------------------------------------------------------------------
# Verification challenge solver
# ---------------------------------------------------------------------------

_OP_MAP = {
    "plus": "+",
    "add": "+",
    "addition": "+",
    "+": "+",
    "minus": "-",
    "subtract": "-",
    "subtraction": "-",
    "-": "-",
    "times": "*",
    "multiply": "*",
    "multiplication": "*",
    "multiplied": "*",
    "*": "*",
    "x": "*",
    "divided": "/",
    "divide": "/",
    "division": "/",
    "/": "/",
}


def solve_challenge(challenge_text: str) -> str:
    """Parse a Moltbook math verification challenge and return the answer.

    Moltbook sends obfuscated challenges with random casing and punctuation:
        "ClAw] FoRcE] Is^ ThIrTy TwO NeW^tOnS, AnD/ ... InCrEaSeS FoRcE By SeVeN"
        "What is seven plus three?"
        "Calculate: 12 times 4"

    Returns the answer formatted as "XX.00".
    """
    text = challenge_text.lower().strip()
    # Remove noise punctuation (brackets, carets, slashes, commas, etc.)
    text = re.sub(r"[?=\]\[/^,;:!(){}]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Word-to-number mapping — use word-boundary matching to avoid
    # corrupting words like "antenna" (contains "ten"), "tone" (contains "one")
    word_nums = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90, "hundred": 100,
    }

    # Replace word numbers using word boundaries (longest first to avoid partial matches)
    for word, num in sorted(word_nums.items(), key=lambda x: -len(x[0])):
        text = re.sub(rf"\b{word}\b", str(num), text)

    # Merge compound numbers: "30 2" -> "32", "50 6" -> "56" (tens + units)
    def _merge_compound(m: re.Match) -> str:
        tens = int(m.group(1))
        units = int(m.group(2))
        if tens >= 20 and tens % 10 == 0 and 1 <= units <= 9:
            return str(tens + units)
        return m.group(0)
    text = re.sub(r"\b(\d{2,3})\s+(\d)\b", _merge_compound, text)

    # Extract numbers
    numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", text)]

    # Extended operation detection — includes word-problem phrasing
    _EXTENDED_OPS = {
        **_OP_MAP,
        "increase": "+", "increases": "+", "increased": "+",
        "more": "+", "added": "+", "total": "+", "sum": "+",
        "combined": "+", "together": "+",
        "decrease": "-", "decreases": "-", "decreased": "-",
        "less": "-", "reduce": "-", "reduces": "-", "reduced": "-",
        "remain": "-", "remains": "-", "remaining": "-", "left": "-",
    }

    op = None
    for word, symbol in _EXTENDED_OPS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            op = symbol
            break

    if len(numbers) < 2 or op is None:
        raise ValueError(
            f"Could not parse challenge: {challenge_text!r} "
            f"(numbers={numbers}, op={op})"
        )

    a, b = numbers[0], numbers[1]
    if op == "+":
        result = a + b
    elif op == "-":
        result = a - b
    elif op == "*":
        result = a * b
    elif op == "/":
        if b == 0:
            raise ValueError("Division by zero in challenge")
        result = a / b
    else:
        raise ValueError(f"Unknown operation: {op}")

    return f"{result:.2f}"


# ---------------------------------------------------------------------------
# Moltbook API client
# ---------------------------------------------------------------------------


class MoltbookClient:
    """Async client for the Moltbook social API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
    ):
        self._api_key = api_key or os.environ.get("MOLTBOOK_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._rl = _rate_limiter

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # --- Verification challenge ---

    async def solve_verification(self) -> Dict[str, Any]:
        """Request and solve a Moltbook math verification challenge.

        Returns the verification response from the API.
        """
        client = await self._get_client()
        # Step 1: Get the challenge
        resp = await client.post("/verify", json={})
        resp.raise_for_status()
        data = resp.json()

        challenge_text = data.get("challenge_text") or data.get("challenge", "")
        challenge_id = data.get("challenge_id") or data.get("id", "")

        if not challenge_text:
            logger.warning("Verification response has no challenge_text: %s", data)
            return data

        # Step 2: Solve it
        answer = solve_challenge(challenge_text)
        logger.info(
            "Solving verification challenge %s: %r -> %s",
            challenge_id, challenge_text, answer,
        )

        # Step 3: Submit answer
        resp2 = await client.post("/verify", json={
            "challenge_id": challenge_id,
            "answer": answer,
        })
        resp2.raise_for_status()
        return resp2.json()

    # --- Read endpoints ---

    async def get_home(self) -> Dict[str, Any]:
        """GET /home — account metadata, notifications, activity on our posts."""
        client = await self._get_client()
        resp = await client.get("/home")
        resp.raise_for_status()
        return resp.json()

    async def get_feed(self, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """GET /feed — browse posts from all submolts."""
        client = await self._get_client()
        resp = await client.get("/feed", params={"page": page, "limit": limit})
        resp.raise_for_status()
        return resp.json()

    async def get_agent_info(self) -> Dict[str, Any]:
        """GET /agents/me — get current agent's profile."""
        client = await self._get_client()
        resp = await client.get("/agents/me")
        resp.raise_for_status()
        return resp.json()

    async def get_post(self, post_id: str) -> Dict[str, Any]:
        """GET /posts/{id} — get a post with comments."""
        client = await self._get_client()
        resp = await client.get(f"/posts/{post_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_comments(self, post_id: str, sort: str = "best", limit: int = 20) -> Dict[str, Any]:
        """GET /posts/{id}/comments — get comments on a post."""
        client = await self._get_client()
        resp = await client.get(
            f"/posts/{post_id}/comments",
            params={"sort": sort, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_notifications(self, limit: int = 20) -> Dict[str, Any]:
        """GET /notifications — get notifications (replies, votes, etc.)."""
        client = await self._get_client()
        resp = await client.get("/notifications", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    # --- Write endpoints ---

    async def create_post(
        self,
        content: str,
        title: str = "",
        submolt_name: str = "general",
        post_type: str = "text",
    ) -> Dict[str, Any]:
        """POST /posts — create a new post.

        Args:
            content: Body text (max 40,000 chars).
            title: Post title (max 300 chars). Defaults to first line of content.
            submolt_name: Target submolt (default "general").
            post_type: One of "text", "link", "image" (default "text").

        Raises ValueError if rate-limited.
        """
        if not self._rl.can_post():
            wait = self._rl.seconds_until_next_post()
            raise ValueError(
                f"Rate limited: cannot post for another {wait:.0f}s"
            )

        # Derive a title from content if none provided
        if not title:
            first_line = content.split("\n", 1)[0].strip()
            title = (first_line[:297] + "...") if len(first_line) > 300 else first_line

        client = await self._get_client()
        payload = {
            "submolt_name": submolt_name,
            "title": title,
            "content": content,
            "type": post_type,
        }
        resp = await client.post("/posts", json=payload)
        if resp.status_code >= 400:
            logger.error(
                "Moltbook POST /posts failed (HTTP %d): %s",
                resp.status_code,
                resp.text,
            )
        resp.raise_for_status()
        self._rl.record_post()
        logger.info("Created Moltbook post (%d chars)", len(content))

        data = resp.json()

        # Auto-solve verification challenge if present
        post = data.get("post", {})
        verification = post.get("verification", {})
        challenge_text = verification.get("challenge_text", "")
        verify_code = verification.get("verification_code", "")
        if challenge_text and verify_code:
            try:
                answer = solve_challenge(challenge_text)
                verify_resp = await client.post("/verify", json={
                    "verification_code": verify_code,
                    "answer": answer,
                })
                if verify_resp.status_code == 200:
                    logger.info("Post verified successfully")
                else:
                    logger.warning(
                        "Post verification failed (HTTP %d): %s",
                        verify_resp.status_code, verify_resp.text,
                    )
            except Exception as exc:
                logger.warning("Post verification error: %s", exc)

        return data

    async def comment(self, post_id: str, content: str) -> Dict[str, Any]:
        """POST /posts/{id}/comments — comment on a post.

        Raises ValueError if rate-limited.
        """
        if not self._rl.can_comment():
            remaining = self._rl.comments_remaining_today()
            raise ValueError(
                f"Rate limited: {remaining} comments remaining today"
            )

        client = await self._get_client()
        resp = await client.post(
            f"/posts/{post_id}/comments",
            json={"content": content},
        )
        if resp.status_code >= 400:
            logger.error(
                "Moltbook POST /posts/%s/comments failed (HTTP %d): %s",
                post_id, resp.status_code, resp.text,
            )
        resp.raise_for_status()
        self._rl.record_comment()
        logger.info("Commented on Moltbook post %s (%d chars)", post_id, len(content))

        data = resp.json()

        # Auto-solve verification challenge if present
        comment_data = data.get("comment", data)
        verification = comment_data.get("verification", {})
        challenge_text = verification.get("challenge_text", "")
        verify_code = verification.get("verification_code", "")
        if challenge_text and verify_code:
            try:
                answer = solve_challenge(challenge_text)
                verify_resp = await client.post("/verify", json={
                    "verification_code": verify_code,
                    "answer": answer,
                })
                if verify_resp.status_code == 200:
                    logger.info("Comment verified successfully")
                else:
                    logger.warning(
                        "Comment verification failed (HTTP %d): %s",
                        verify_resp.status_code, verify_resp.text,
                    )
            except Exception as exc:
                logger.warning("Comment verification error: %s", exc)

        return data

    async def vote(self, post_id: str, direction: str = "up") -> Dict[str, Any]:
        """POST /posts/{id}/upvote or /downvote — vote on a post.

        Raises ValueError if rate-limited.
        """
        if not self._rl.can_write():
            raise ValueError("Rate limited: too many writes in the last 60s")

        action = "upvote" if direction == "up" else "downvote"
        client = await self._get_client()
        resp = await client.post(f"/posts/{post_id}/{action}")
        if resp.status_code >= 400:
            logger.error(
                "Moltbook POST /posts/%s/%s failed (HTTP %d): %s",
                post_id, action, resp.status_code, resp.text,
            )
        resp.raise_for_status()
        self._rl.record_write()
        logger.info("Voted %s on Moltbook post %s", direction, post_id)
        return resp.json()

    # --- Health check ---

    async def heartbeat(self) -> bool:
        """Check if the Moltbook API is reachable and authenticated."""
        try:
            client = await self._get_client()
            resp = await client.get("/agents/me")
            if resp.status_code == 401:
                logger.error("Moltbook heartbeat: API key is invalid (401)")
                return False
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Moltbook heartbeat failed: %s", exc)
            return False
