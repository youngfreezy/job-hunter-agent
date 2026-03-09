// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

test.describe("Coach Chat Live", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("coach chat revises the coached resume before approval", async ({ page }) => {
    test.setTimeout(240_000);

    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Python", "Backend Engineer"],
        locations: ["Remote"],
        remote_only: true,
        salary_min: 140000,
        resume_text:
          "Taylor Example\nSenior Backend Engineer\n8 years building Python and FastAPI backend systems.\n" +
          "Led API platform work, AWS deployments, Docker-based services, PostgreSQL, and Redis.",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    await page.goto(`/session/${sessionId}`);

    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible({ timeout: 180_000 });
    await expect(dialog.getByText("Review Your Coached Resume")).toBeVisible();

    const chatInput = dialog.getByPlaceholder("Ask the coach to revise your resume or strategy...");
    await chatInput.fill(
      "Revise the resume and include the exact phrase FastAPI backend engineer."
    );
    await expect(chatInput).toHaveValue(
      "Revise the resume and include the exact phrase FastAPI backend engineer."
    );
    await dialog.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText(/FastAPI backend engineer/i).first()).toBeVisible({
      timeout: 120_000,
    });

    await dialog.getByRole("button", { name: /Approve|Continue/i }).click();
    await expect(dialog).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/discover|search|finding/i).first()).toBeVisible({
      timeout: 30_000,
    });
  });
});
