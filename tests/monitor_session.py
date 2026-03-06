"""Monitor an active session and handle HITL steps (coach review, shortlist review)."""
import asyncio
import sys
import aiohttp

SESSION_ID = sys.argv[1] if len(sys.argv) > 1 else "e72de617-ad6d-438c-8f5a-2c7750d6f1d2"
API = f"http://localhost:8000/api/sessions/{SESSION_ID}"

async def main():
    last_status = ""
    coach_done = False
    shortlist_done = False
    start = asyncio.get_event_loop().time()

    print(f"Monitoring session: {SESSION_ID}")
    print(f"API: {API}\n")

    while True:
        elapsed = int(asyncio.get_event_loop().time() - start)
        if elapsed > 900:  # 15 min max
            print("\nTimeout (15 min)")
            break

        async with aiohttp.ClientSession() as session:
            async with session.get(API) as resp:
                if resp.status != 200:
                    print(f"[{elapsed}s] API {resp.status}")
                    await asyncio.sleep(5)
                    continue

                data = await resp.json()
                status = data.get("status", "unknown")
                submitted = data.get("applications_submitted", [])
                failed = data.get("applications_failed", [])
                skipped = data.get("applications_skipped", [])
                discovered = data.get("discovered_jobs", [])
                scored = data.get("scored_jobs", [])
                queue = data.get("application_queue", [])
                agents = data.get("agent_statuses", {})

                if status != last_status:
                    print(f"[{elapsed}s] STATUS: {status}")
                    print(f"  Discovered: {len(discovered)}, Scored: {len(scored)}, Queue: {len(queue)}")
                    print(f"  Submitted: {len(submitted)}, Failed: {len(failed)}, Skipped: {len(skipped)}")
                    print(f"  Agents: {agents}")
                    last_status = status

                # Handle coach review
                if status == "awaiting_coach_review" and not coach_done:
                    print(f"\n[{elapsed}s] Approving coach review...")
                    async with session.post(f"{API}/coach-review", json={"approved": True}) as r:
                        print(f"  Response: {r.status}")
                        coach_done = True

                # Handle shortlist review
                if status == "awaiting_review" and not shortlist_done:
                    # Get all scored job IDs
                    job_ids = []
                    for sj in scored:
                        if isinstance(sj, dict):
                            job = sj.get("job", {})
                            job_id = job.get("id", "") if isinstance(job, dict) else ""
                        else:
                            job_id = getattr(getattr(sj, "job", None), "id", "")
                        if job_id:
                            job_ids.append(job_id)

                    if job_ids:
                        print(f"\n[{elapsed}s] Approving shortlist ({len(job_ids)} jobs)...")
                        async with session.post(f"{API}/review", json={"approved_job_ids": job_ids}) as r:
                            print(f"  Response: {r.status}")
                            if r.status in (200, 202):
                                shortlist_done = True
                    else:
                        print(f"\n[{elapsed}s] No scored jobs found for shortlist review")

                # Done?
                if status in ("completed", "failed"):
                    print(f"\n=== SESSION {status.upper()} ===")
                    print(f"  Submitted: {len(submitted)}")
                    for s in submitted:
                        if isinstance(s, dict):
                            print(f"    - {s.get('job_id', '?')}: {s.get('status', '?')}")
                    print(f"  Failed: {len(failed)}")
                    for f in failed:
                        if isinstance(f, dict):
                            print(f"    - {f.get('job_id', '?')}: {f.get('error_message', '?')}")
                    print(f"  Skipped: {len(skipped)}")
                    break

                if status == "paused":
                    print(f"\n=== SESSION PAUSED ===")
                    print(f"  Errors: {data.get('errors', [])}")
                    break

        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
