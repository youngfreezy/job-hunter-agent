"""Quick session monitor with auto-approve."""
import asyncio
import aiohttp
import sys

SESSION_ID = sys.argv[1] if len(sys.argv) > 1 else "e72de617-ad6d-438c-8f5a-2c7750d6f1d2"
API = f"http://localhost:8000/api/sessions/{SESSION_ID}"

async def monitor():
    last_status = ""
    shortlist_done = False
    for i in range(180):
        await asyncio.sleep(5)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(API) as r:
                    d = await r.json()
                    st = d.get("status", "?")
                    disc = len(d.get("discovered_jobs", []))
                    scored = len(d.get("scored_jobs", []))
                    q = len(d.get("application_queue", []))
                    sub = len(d.get("applications_submitted", []))
                    fail = len(d.get("applications_failed", []))
                    skip = len(d.get("applications_skipped", []))
                    if st != last_status or i % 12 == 0:
                        print(f"[{i*5}s] {st} | disc={disc} scored={scored} q={q} sub={sub} fail={fail} skip={skip}")
                        last_status = st

                    if st == "awaiting_review" and not shortlist_done:
                        job_ids = []
                        for sj in d.get("scored_jobs", []):
                            jid = sj.get("job", {}).get("id", "") if isinstance(sj, dict) else ""
                            if jid:
                                job_ids.append(jid)
                        if job_ids:
                            async with s.post(f"{API}/review", json={"approved_job_ids": job_ids}) as r2:
                                print(f"  >> Approved {len(job_ids)} jobs: {r2.status}")
                                shortlist_done = True

                    if st in ("completed", "failed", "paused"):
                        for sub_item in d.get("applications_submitted", []):
                            if isinstance(sub_item, dict):
                                print(f"  SUBMITTED: {sub_item.get('job_id', '?')}")
                        for f_item in d.get("applications_failed", []):
                            if isinstance(f_item, dict):
                                print(f"  FAILED: {f_item.get('job_id', '?')} - {f_item.get('error_message', '?')}")
                        print(f"  Errors: {d.get('errors', [])}")
                        break
        except Exception as e:
            print(f"[{i*5}s] Error: {e}")

asyncio.run(monitor())
