import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

test.describe("Manual Apply (Live Integration)", () => {
  test("manual-apply UI shows live submission with cover letter and tailored resume", async ({
    page,
  }) => {
    test.setTimeout(420_000);

    await login(page);

    const createRes = await page.request.post(`${API_BASE}/api/sessions/test-apply`, {
      data: {
        job_url: "https://job-boards.greenhouse.io/vercel/jobs/5708732004",
        job_title: "Account Executive, Commercial Install Base",
        company: "Vercel",
        resume_text:
          "Fareez Ahmed\nAI Engineer\nfareez@example.com\nPython, FastAPI, LangGraph, Playwright, TypeScript",
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    // This job frequently pauses at CAPTCHA/manual intervention.
    await page.waitForTimeout(15_000);
    await page.request.post(`${API_BASE}/api/sessions/${sessionId}/resume-intervention`);

    let entries: Array<Record<string, unknown>> = [];
    for (let i = 0; i < 80; i++) {
      const logRes = await page.request.get(`${API_BASE}/api/sessions/${sessionId}/application-log`);
      expect(logRes.status()).toBe(200);
      const body = await logRes.json();
      entries = body.entries ?? [];
      if (entries.length > 0) break;
      await page.waitForTimeout(5_000);
    }
    expect(entries.length).toBeGreaterThan(0);

    const latest = entries[entries.length - 1] as {
      status?: string;
      cover_letter?: string;
      tailored_resume?: { tailored_text?: string } | null;
    };
    expect(latest.status).toBe("submitted");
    expect((latest.cover_letter ?? "").length).toBeGreaterThan(100);
    expect((latest.tailored_resume?.tailored_text ?? "").length).toBeGreaterThan(50);

    await page.goto(`/session/${sessionId}/manual-apply`);

    await expect(page.getByText("Application Log")).toBeVisible();
    await expect(page.getByText("Account Executive, Commercial Install Base")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText("submitted", { exact: true }).first()).toBeVisible();

    await page.getByText("Details").first().click();
    await expect(page.getByRole("heading", { name: "Cover Letter" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tailored Resume" })).toBeVisible();
  });
});
