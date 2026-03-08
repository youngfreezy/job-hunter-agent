// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { expect, test } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

async function waitForSessionStatus(
  page: import("@playwright/test").Page,
  sessionId: string,
  predicate: (status: string, payload: Record<string, unknown>) => boolean,
  timeoutMs = 30000
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + timeoutMs;
  let last: Record<string, unknown> = {};

  while (Date.now() < deadline) {
    const res = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`);
    expect(res.ok()).toBeTruthy();
    last = (await res.json()) as Record<string, unknown>;
    if (predicate(String(last.status || ""), last)) {
      return last;
    }
    await page.waitForTimeout(1000);
  }

  throw new Error(`Timed out waiting for session status. Last payload: ${JSON.stringify(last)}`);
}

test.describe("Live Pause/Resume Steering", () => {
  test("supervisor can pause after coach review and resume the workflow", async ({ page }) => {
    test.setTimeout(240_000);

    await login(page);

    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Python", "Backend Engineer"],
        locations: ["Remote"],
        remote_only: true,
        salary_min: 140000,
        resume_text:
          "Taylor Example\nSenior Backend Engineer\n8 years building Python and FastAPI systems with AWS, Docker, PostgreSQL, and Redis.",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.ok()).toBeTruthy();
    const { session_id: sessionId } = await createRes.json();

    await page.goto(`/session/${sessionId}`);

    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible({ timeout: 180_000 });
    await expect(dialog.getByText("Review Your Coached Resume")).toBeVisible();

    const steerRes = await page.request.post(`${API_BASE}/api/sessions/${sessionId}/steer`, {
      data: { message: "Pause the workflow after this coach review." },
    });
    expect(steerRes.ok()).toBeTruthy();

    const approveRes = await page.request.post(
      `${API_BASE}/api/sessions/${sessionId}/coach-review`,
      { data: { approved: true } }
    );
    expect(approveRes.ok()).toBeTruthy();

    await waitForSessionStatus(page, sessionId, (status) => status === "paused", 60000);
    await expect(page.getByText(/paused/i).first()).toBeVisible({ timeout: 30000 });

    const resumeRes = await page.request.post(`${API_BASE}/api/sessions/${sessionId}/steer`, {
      data: { message: "Resume the workflow now." },
    });
    expect(resumeRes.ok()).toBeTruthy();

    await waitForSessionStatus(
      page,
      sessionId,
      (status) => status !== "paused" && status !== "awaiting_coach_review",
      60000
    );
    await expect(page.getByText(/discover|search|finding/i).first()).toBeVisible({ timeout: 30000 });
  });
});
