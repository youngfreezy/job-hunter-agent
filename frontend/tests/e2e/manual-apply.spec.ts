// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

test.describe("Manual Apply / Application Log", () => {
  const sessionId = "manual-apply-test-001";

  const mockEntries = [
    {
      status: "submitted",
      job: {
        id: "job-1",
        title: "Senior React Engineer",
        company: "Acme Corp",
        url: "https://boards.greenhouse.io/acme/jobs/1",
        board: "linkedin",
        location: "Remote",
      },
      error: null,
      cover_letter: "Dear Hiring Manager,\n\nI am excited to apply...",
      tailored_resume: {
        tailored_text: "John Doe\nSenior React Engineer\n...",
        fit_score: 87,
        changes_made: [],
      },
      duration: 45,
      submitted_at: new Date().toISOString(),
    },
    {
      status: "failed",
      job: {
        id: "job-2",
        title: "Full Stack Developer",
        company: "Widget Inc",
        url: "https://boards.greenhouse.io/widget/jobs/2",
        board: "indeed",
        location: "New York, NY",
      },
      error: "Submit clicked but no confirmation page detected",
      cover_letter: "Dear Widget Team,\n\nI am writing to express...",
      tailored_resume: null,
      duration: 30,
      submitted_at: null,
    },
    {
      status: "skipped",
      job: {
        id: "job-3",
        title: "Backend Engineer",
        company: "StartupCo",
        url: "https://startup.co/careers/3",
        board: "glassdoor",
        location: "San Francisco, CA",
      },
      error: "auth_required",
      cover_letter: "",
      tailored_resume: null,
      duration: 5,
      submitted_at: null,
    },
  ];

  test.beforeEach(async ({ page }) => {
    // Log in first (routes are protected)
    await login(page);

    // Mock the application log API (correct endpoint)
    await page.route(`**/api/sessions/${sessionId}/application-log`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ entries: mockEntries }),
      });
    });
  });

  test("loads and shows all application entries", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    await expect(page.getByText("Application Log")).toBeVisible();
    await expect(page.getByText("Senior React Engineer")).toBeVisible();
    await expect(page.getByText("Full Stack Developer")).toBeVisible();
    await expect(page.getByText("Backend Engineer")).toBeVisible();
  });

  test("shows correct tab counts", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    await expect(page.getByText("All (3)")).toBeVisible();
    await expect(page.getByText("Submitted (1)")).toBeVisible();
    await expect(page.getByText("Failed (1)")).toBeVisible();
    await expect(page.getByText("Skipped (1)")).toBeVisible();
  });

  test("filters by tab", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    // Wait for entries to load
    await expect(page.getByText("All (3)")).toBeVisible();

    // Click Failed tab
    await page.getByText("Failed (1)").click();
    await expect(page.getByText("Full Stack Developer")).toBeVisible();
    await expect(page.getByText("Senior React Engineer")).not.toBeVisible();

    // Click Submitted tab
    await page.getByText("Submitted (1)").click();
    await expect(page.getByText("Senior React Engineer")).toBeVisible();
    await expect(page.getByText("Full Stack Developer")).not.toBeVisible();
  });

  test("shows status badges", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    // Wait for data to load
    await expect(page.getByText("Application Log")).toBeVisible();
    await expect(page.getByText("Senior React Engineer")).toBeVisible();

    await expect(page.getByText("submitted", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("failed", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("skipped", { exact: true }).first()).toBeVisible();
  });

  test("expands details to show cover letter", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    // Wait for entries to load
    await expect(page.getByText("Senior React Engineer")).toBeVisible();

    // Click Details button on the first entry (submitted one)
    await page.getByText("Details").first().click();

    // Cover letter should be visible
    await expect(page.getByRole("heading", { name: "Cover Letter" })).toBeVisible();
    await expect(page.getByText("Dear Hiring Manager,")).toBeVisible();
  });

  test("has Apply buttons linking to job URLs", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    // Wait for entries to load
    await expect(page.getByText("Senior React Engineer")).toBeVisible();

    const applyButtons = page.locator('a[href*="greenhouse.io"]');
    const count = await applyButtons.count();
    expect(count).toBeGreaterThan(0);

    // First Apply button should link to the job URL
    const href = await applyButtons.first().getAttribute("href");
    expect(href).toBeTruthy();
  });

  test("shows error message for failed applications", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    // Wait for entries to load
    await expect(page.getByText("Full Stack Developer")).toBeVisible();

    await expect(page.getByText("Submit clicked but no confirmation page detected")).toBeVisible();
  });

  test("shows empty state when no applications", async ({ page }) => {
    // Override the route mock for this specific test
    await page.route(`**/api/sessions/${sessionId}/application-log`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ entries: [] }),
      });
    });

    await page.goto(`/session/${sessionId}/manual-apply`);

    await expect(page.getByText("No applications yet")).toBeVisible();
  });

  test("nav links are present", async ({ page }) => {
    await page.goto(`/session/${sessionId}/manual-apply`);

    await expect(page.getByText("JobHunter Agent").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Activity" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Manual Apply" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  });
});
