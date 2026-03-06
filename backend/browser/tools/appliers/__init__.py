"""Applier registry -- dispatches to the right applier based on board + ATS type."""

from __future__ import annotations

import logging
from typing import Any

from backend.shared.models.schemas import ATSType

from .base import BaseApplier

logger = logging.getLogger(__name__)


def get_applier(board: str, ats_type: ATSType, page: Any, session_id: str) -> BaseApplier:
    """Select the best applier based on board + ATS type.

    Priority:
    1. Board-specific (linkedin, indeed, glassdoor, ziprecruiter)
    2. ATS-specific (greenhouse, lever, workday)
    3. Generic (form_filler + submit detection)
    """
    # Board-specific appliers
    if board == "linkedin":
        from .linkedin import LinkedInApplier
        return LinkedInApplier(page, session_id)
    if board == "indeed":
        from .indeed import IndeedApplier
        return IndeedApplier(page, session_id)
    if board == "glassdoor":
        from .glassdoor import GlassdoorApplier
        return GlassdoorApplier(page, session_id)
    if board == "ziprecruiter":
        from .ziprecruiter import ZipRecruiterApplier
        return ZipRecruiterApplier(page, session_id)

    # ATS-specific appliers
    if ats_type == ATSType.GREENHOUSE:
        from .greenhouse import GreenhouseApplier
        return GreenhouseApplier(page, session_id)
    if ats_type == ATSType.LEVER:
        from .lever import LeverApplier
        return LeverApplier(page, session_id)
    if ats_type == ATSType.WORKDAY:
        from .workday import WorkdayApplier
        return WorkdayApplier(page, session_id)

    # Generic fallback
    from .generic import GenericApplier
    logger.info("Using generic applier for board=%s, ats=%s", board, ats_type.value)
    return GenericApplier(page, session_id)
