// Copyright (c) 2026 V2 Software LLC. All rights reserved.

/**
 * Full integration test: Wizard → Session Page → SSE Events → Keywords
 *
 * This test goes through the REAL flow (no API mocking) against the
 * running backend. It verifies:
 * 1. Wizard steps complete properly
 * 2. Form submission creates a session
 * 3. Redirect to session page works
 * 4. Keywords appear in sidebar
 * 5. SSE events stream in the status feed
 * 6. Pipeline progresses past intake
 */
import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";
const API_BASE = "http://localhost:8000";
const RESUME_TEXT =
  "Senior Software Engineer with 10 years of experience in React, Python, " +
  "and distributed systems. Built multiple AI-native applications using " +
  "LangGraph, LangChain, and RAG pipelines. Expert in TypeScript, Node.js, " +
  "and AWS cloud services.";
const RESUME_FILE = {
  name: "test-resume-full.txt",
  mimeType: "text/plain",
  buffer: Buffer.from(RESUME_TEXT),
};

test.describe("Full Wizard → Session Flow (Integration)", () => {

  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("complete wizard and verify session page loads with keywords and events", async ({
    page,
  }) => {
    test.setTimeout(60_000);

    // Step 1: Navigate to wizard
    await page.goto("/session/new");
    await expect(
      page.getByRole("heading", { name: "New Session" })
    ).toBeVisible();
    await expect(page.getByText("Job Search", { exact: true })).toBeVisible();

    // Step 1: Fill keywords
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React, Python, LangGraph");
    await page.waitForTimeout(500);

    // Verify keyword badges appear
    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Python").first()).toBeVisible();
    await expect(page.getByText("LangGraph").first()).toBeVisible();

    // Check "Remote only"
    await page.getByText("Remote only").click();
    await page.waitForTimeout(300);

    // Click Next
    await page.getByRole("button", { name: "Next" }).click();
    await page.waitForTimeout(500);

    // Step 2: Should be on Resume & Profile
    await expect(
      page.getByText("Your Resume", { exact: true }).first()
    ).toBeVisible();

    // Upload resume file
    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume-full.txt").first()).toBeVisible();
    await page.waitForTimeout(500);

    // Click Next
    await page.getByRole("button", { name: "Next" }).click();
    await page.waitForTimeout(500);

    // Step 3: Should be on Review & Launch
    await expect(
      page.getByText("Review & Launch", { exact: true }).first()
    ).toBeVisible();

    // Verify review shows our data
    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Remote only")).toBeVisible();
    await page.waitForTimeout(1000);

    // Submit the form
    await page.getByRole("button", { name: "Start Job Hunt Session" }).click();

    // Wait for redirect to session page
    await page.waitForURL(/\/session\/[a-f0-9-]+/, { timeout: 15_000 });
    await page.waitForTimeout(2000);

    // Verify we're on the session page
    await expect(page.getByText("JobHunter Agent").first()).toBeVisible();
    await expect(page.getByText("Live Status")).toBeVisible();

    // Verify keywords appear in sidebar (as individual badges)
    await expect(page.getByText("React").first()).toBeVisible({
      timeout: 10_000,
    });

    // Verify SSE events are streaming
    await expect(
      page.getByText("Starting your job hunt session...")
    ).toBeVisible({
      timeout: 10_000,
    });

    // Wait for coaching to start — STEP_LABELS shows "Coach"
    await expect(page.getByText("Coach").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("session page refresh preserves keywords and replays events", async ({
    page,
  }) => {
    test.setTimeout(60_000);

    // Create a session via the API directly
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["TypeScript", "AI"],
        locations: ["Remote"],
        remote_only: true,
        salary_min: null,
        resume_text: "Experienced TypeScript developer with AI expertise.",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id } = await createRes.json();

    // Wait for pipeline to start and emit some events
    await page.waitForTimeout(3000);

    // Navigate to the session page
    await page.goto(`/session/${session_id}`);
    await page.waitForTimeout(2000);

    // Verify keywords from registry/checkpointer (individual badges)
    await expect(page.getByText("TypeScript").first()).toBeVisible({
      timeout: 10_000,
    });

    // Verify replayed SSE events
    await expect(
      page.getByText("Starting your job hunt session...")
    ).toBeVisible({
      timeout: 10_000,
    });

    // Refresh the page
    await page.reload();
    await page.waitForTimeout(2000);

    // Keywords should still be visible after refresh
    await expect(page.getByText("TypeScript").first()).toBeVisible({
      timeout: 10_000,
    });

    // Events should be replayed
    await expect(
      page.getByText("Starting your job hunt session...")
    ).toBeVisible({
      timeout: 10_000,
    });
  });

  test("dashboard shows created sessions", async ({ page }) => {
    test.setTimeout(30_000);

    // Create a session via API
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Dashboard Test"],
        locations: [],
        remote_only: false,
        salary_min: null,
        resume_text: "Test resume for dashboard.",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);

    // Navigate to dashboard
    await page.goto("/dashboard");
    await page.waitForTimeout(2000);

    // Should show the session keywords
    await expect(page.getByText("Dashboard Test").first()).toBeVisible({
      timeout: 10_000,
    });
  });
});
