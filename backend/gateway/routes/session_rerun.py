"""Build a bounded fresh launch from an existing session checkpoint."""
from typing import Any

from backend.shared.models.schemas import SessionConfig, StartSessionRequest


def build_rerun_request(
    state: dict[str, Any], overrides: dict[str, Any], resume_id: str,
) -> StartSessionRequest:
    # A summary row cannot recover a URL scope or job limit. Refuse to guess.
    required = {"keywords", "locations", "remote_only", "salary_min", "session_config", "job_urls", "resume_text"}
    if not required.issubset(state) or not state.get("resume_text"):
        raise ValueError("Original session settings are unavailable. Start a new search or use Quick Apply.")
    config = state["session_config"]
    if isinstance(config, SessionConfig):
        config = config.model_dump()
    if not isinstance(config, dict) or "max_jobs" not in config:
        raise ValueError("Original application limit is unavailable. Start a new search.")
    urls = list(state["job_urls"] or config.get("job_urls", []))
    if config and config.get("discovery_mode") == "manual_urls" and not urls:
        raise ValueError("Original job links are unavailable. Paste the job links in Quick Apply.")
    # Approval of an earlier shortlist never authorizes a new discovered shortlist.
    # Quick Apply derives its own review policy from the retained explicit URLs.
    preferences = {key: value for key, value in (state.get("preferences") or {}).items()
                   if not key.startswith("_")}
    fields = {key: state.get(key) for key in
              ("keywords", "locations", "remote_only", "salary_min", "resume_text", "linkedin_url")}
    fields.update({key: value for key, value in overrides.items() if value is not None})
    return StartSessionRequest(
        **fields, search_radius=state.get("search_radius", 100), resume_uuid=resume_id,
        preferences=preferences, config=config, job_urls=urls,
    )
