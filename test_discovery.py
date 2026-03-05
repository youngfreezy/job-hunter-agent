"""Quick isolation test for browser-use discovery on a single board."""
import asyncio
import sys
sys.path.insert(0, ".")

from backend.shared.models.schemas import JobBoard, SearchConfig
from backend.browser.tools.browser_use_discovery import discover_board


async def main():
    search_config = SearchConfig(
        keywords=["AI Engineer"],
        locations=["Remote"],
        remote_only=True,
        salary_min=None,
    )

    # Test with LinkedIn (least bot-detection issues)
    print("Testing discovery on LinkedIn...")
    jobs = await discover_board(
        board=JobBoard.LINKEDIN,
        search_config=search_config,
        session_id="test-session",
        max_results=5,
    )

    print(f"\nFound {len(jobs)} jobs:")
    for j in jobs:
        print(f"  - {j.title} @ {j.company} | {j.url}")

    if not jobs:
        print("WARNING: No jobs found!")
        return 1
    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
