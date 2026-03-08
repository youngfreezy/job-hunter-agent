// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

test.describe("Live Steering Integration", () => {
  test("chat steering uses the live LLM judge and returns a status-grounded reply", async ({
    page,
  }) => {
    test.setTimeout(180_000);

    await login(page);

    // Create a real session via backend API (no route mocking).
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Python", "Backend Engineer"],
        locations: ["Remote"],
        remote_only: true,
        salary_min: 120000,
        resume_text:
          "Test User\nSenior Backend Engineer\ntest@example.com\n5 years Python, FastAPI, AWS, Docker, PostgreSQL",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    await page.goto(`/session/${sessionId}`);
    await expect(page.getByText("Session Steering")).toBeVisible({
      timeout: 20_000,
    });

    const command = "what are you doing right now?";
    await page.getByPlaceholder("Ask the agent to adjust...").fill(command);
    await page.getByRole("button", { name: "Send" }).click();

    const steeringPanel = page.locator("div").filter({
      has: page.getByText("Session Steering"),
    });

    // User message should render in chat immediately.
    await expect(steeringPanel.getByText(command)).toBeVisible({
      timeout: 10_000,
    });

    // The live steering judge should answer from session context rather than
    // echoing a canned acknowledgement.
    await expect(
      steeringPanel.getByText(/^Right now I'm/i).first()
    ).toBeVisible({
      timeout: 20_000,
    });
  });
});
