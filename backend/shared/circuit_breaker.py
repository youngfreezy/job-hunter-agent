# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Circuit breaker pattern for external API calls.

Prevents cascading failures by tracking error rates and temporarily
halting requests to services that are consistently failing.

Usage:
    breaker = CircuitBreaker("openai", failure_threshold=5, recovery_timeout=60)
    async with breaker:
        result = await llm.ainvoke(messages)
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing — reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and requests are rejected."""

    def __init__(self, name: str, retry_after: float):
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. "
            f"Retry after {retry_after:.0f}s."
        )


class CircuitBreaker:
    """Thread-safe circuit breaker for external service calls.

    Parameters:
        name: Identifier for the external service (e.g. "openai", "linkedin")
        failure_threshold: Number of consecutive failures before opening the circuit
        recovery_timeout: Seconds to wait before attempting recovery (half-open)
        success_threshold: Consecutive successes in half-open needed to close
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self._last_failure_time and (
                time.monotonic() - self._last_failure_time >= self.recovery_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("Circuit breaker '%s' → HALF_OPEN (testing recovery)", self.name)
        return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info("Circuit breaker '%s' → CLOSED (recovered)", self.name)
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # Recovery attempt failed — re-open
            self._state = CircuitState.OPEN
            logger.warning("Circuit breaker '%s' → OPEN (recovery failed)", self.name)
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker '%s' → OPEN (%d consecutive failures)",
                self.name,
                self._failure_count,
            )

    async def __aenter__(self):
        state = self.state
        if state == CircuitState.OPEN:
            elapsed = time.monotonic() - (self._last_failure_time or 0)
            retry_after = max(0, self.recovery_timeout - elapsed)
            raise CircuitBreakerOpen(self.name, retry_after)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()
        return False  # Don't suppress exceptions


# ---------------------------------------------------------------------------
# Pre-configured breakers for known external services
# ---------------------------------------------------------------------------

llm_breaker = CircuitBreaker(
    "llm",
    failure_threshold=5,
    recovery_timeout=60,
)

job_board_breaker = CircuitBreaker(
    "job_board",
    failure_threshold=8,
    recovery_timeout=120,
)

bright_data_breaker = CircuitBreaker(
    "bright_data",
    failure_threshold=3,
    recovery_timeout=90,
)
