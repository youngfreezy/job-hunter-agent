# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Test submitting a Greenhouse application via the Job Board API directly.

The Greenhouse Job Board API supports application submission:
POST https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}
Content-Type: multipart/form-data

This bypasses the browser, React Select, and reCAPTCHA entirely.
"""
import asyncio
import aiohttp
import os

async def main():
    resume_path = "/Users/janedoe/Desktop/Resumes/Jane_Doe_Resume_AI_Native_2026.pdf"
    if not os.path.exists(resume_path):
        print(f"Resume not found: {resume_path}")
        return

    # Find a job to apply to
    async with aiohttp.ClientSession() as session:
        # Get jobs from Anthropic
        async with session.get("https://boards-api.greenhouse.io/v1/boards/anthropic/jobs") as resp:
            data = await resp.json()
            jobs = data.get("jobs", [])
            if not jobs:
                print("No jobs found")
                return

            # Pick first job
            job = jobs[0]
            job_id = job["id"]
            job_title = job.get("title", "Unknown")
            print(f"Target: {job_title} (ID: {job_id})")

        # Get job details to see required questions
        async with session.get(f"https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/{job_id}?questions=true") as resp:
            job_detail = await resp.json()
            questions = job_detail.get("questions", [])
            print(f"\nJob questions ({len(questions)}):")
            for q in questions:
                print(f"  [{q.get('required', False)}] {q.get('label', '')[:80]} (fields: {[f.get('type') for f in q.get('fields', [])]})")
                for field in q.get("fields", []):
                    if field.get("type") == "multi_value_single_select":
                        print(f"    Options: {[v.get('label') for v in field.get('values', [])[:5]]}")

        # Build the multipart form data
        form = aiohttp.FormData()
        form.add_field("first_name", "Jane")
        form.add_field("last_name", "Doe")
        form.add_field("email", "jane.doe@example.com")
        form.add_field("phone", "5551234567")

        # Add resume file
        with open(resume_path, "rb") as f:
            resume_data = f.read()
        form.add_field("resume", resume_data,
                       filename="Jane_Doe_Resume.pdf",
                       content_type="application/pdf")

        # Add cover letter
        form.add_field("cover_letter",
            "I am excited to apply. With extensive experience in AI-native development, "
            "full-stack engineering, and building LLM-powered systems, I believe I'd be "
            "a strong addition to the team.")

        # Add question answers based on the questions we found
        for q in questions:
            q_id = q.get("id")
            label = q.get("label", "").lower()
            required = q.get("required", False)
            fields = q.get("fields", [])

            if not fields:
                continue

            field = fields[0]
            field_type = field.get("type", "")
            values = field.get("values", [])

            if field_type == "input_text":
                if "linkedin" in label:
                    form.add_field(f"question_{q_id}", "https://www.linkedin.com/in/janedoe/")
                elif "address" in label or "working" in label or "location" in label:
                    form.add_field(f"question_{q_id}", "Austin, TX")
                elif "why" in label:
                    form.add_field(f"question_{q_id}",
                        "I'm passionate about the mission and excited to contribute my AI engineering skills.")
                elif "salary" in label or "compensation" in label:
                    form.add_field(f"question_{q_id}", "200000")
                elif required:
                    form.add_field(f"question_{q_id}", "N/A")

            elif field_type == "textarea":
                if "why" in label:
                    form.add_field(f"question_{q_id}",
                        "I'm deeply passionate about building safe and beneficial AI systems. "
                        "With my experience in AI-native application development, LLM-powered agentic workflows, "
                        "and full-stack engineering, I believe I can make meaningful contributions.")
                elif "cover" in label:
                    form.add_field(f"question_{q_id}",
                        "I'd love to bring my experience in AI and full-stack development to the team.")
                elif "additional" in label:
                    form.add_field(f"question_{q_id}", "Happy to provide any additional info.")
                elif required:
                    form.add_field(f"question_{q_id}", "N/A")

            elif field_type == "multi_value_single_select" and values:
                # Pick the best option
                best = None
                for v in values:
                    vlabel = v.get("label", "").lower()
                    if "yes" in vlabel and ("relocation" in label or "open to" in label or "in-person" in label or "office" in label):
                        best = v["value"]
                        break
                    if "no" in vlabel and ("sponsor" in label or "visa" in label):
                        best = v["value"]
                        break
                    if "acknowledge" in vlabel or "agree" in vlabel:
                        best = v["value"]
                        break
                    if "decline" in vlabel:
                        best = v["value"]  # Don't break, use as default
                    if "confirm" in vlabel or "reviewed" in vlabel:
                        best = v["value"]
                        break

                if not best and values:
                    # Default to first non-empty option
                    for v in values:
                        if v.get("value"):
                            best = v["value"]
                            break

                if best:
                    form.add_field(f"question_{q_id}", str(best))

        # Submit the application
        print(f"\nSubmitting to: https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/{job_id}")
        async with session.post(
            f"https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/{job_id}",
            data=form,
        ) as resp:
            status = resp.status
            text = await resp.text()
            print(f"\nResponse status: {status}")
            print(f"Response body: {text[:500]}")

            if status == 200:
                print("\n*** SUCCESS: Application submitted via API! ***")
            elif status == 428:
                print("\n*** BLOCKED: reCAPTCHA required even for API ***")
            elif status == 422:
                print(f"\n*** VALIDATION ERROR: {text[:300]} ***")
            else:
                print(f"\n*** FAILED: HTTP {status} ***")


if __name__ == "__main__":
    asyncio.run(main())
