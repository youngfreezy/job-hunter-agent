import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

test.describe("Live Session Viewer", () => {
  const mockSessionId = "viewer-test-session-001";

  test.beforeEach(async ({ page }) => {
    await login(page);

    // Mock the GET /api/sessions/:id endpoint
    await page.route(`**/api/sessions/${mockSessionId}`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: mockSessionId,
            status: "discovering",
            keywords: ["React", "Senior Engineer"],
            scored_jobs: [],
            applications_submitted: [],
            applications_failed: [],
            coach_output: null,
            steering_mode: "status",
            applications_used: 0,
            applications_skipped: 0,
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Mock the SSE stream endpoint
    await page.route(
      `**/api/sessions/${mockSessionId}/stream`,
      async (route) => {
        const body = [
          `event: status\ndata: ${JSON.stringify({
            event: "status",
            agent: "orchestrator",
            status: "discovering",
            message: "Pipeline started - discovering jobs",
            timestamp: new Date().toISOString(),
          })}\n\n`,
          `event: discovery\ndata: ${JSON.stringify({
            event: "discovery",
            agent: "discovery",
            status: "discovering",
            message: "Scanning Indeed for React jobs...",
            timestamp: new Date().toISOString(),
          })}\n\n`,
        ].join("");

        await route.fulfill({
          status: 200,
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            Connection: "keep-alive",
          },
          body,
        });
      }
    );
  });

  test("session page loads and shows session data", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Should show JobHunter Agent branding
    await expect(page.getByText("JobHunter Agent").first()).toBeVisible();

    // Should show session status badge — STATUS_LABELS["discovering"] = "Finding Jobs"
    await expect(page.getByText("Finding Jobs").first()).toBeVisible();
  });

  test("shows pipeline progress steps", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Should show pipeline step labels (STEP_LABELS)
    await expect(page.getByText("Setup").first()).toBeVisible();
    await expect(page.getByText("Coach").first()).toBeVisible();
    await expect(page.getByText("Search").first()).toBeVisible();
    await expect(page.getByText("Rank").first()).toBeVisible();
  });

  test("shows the Live Status card", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // The main card title is "Live Status"
    await expect(page.getByText("Live Status")).toBeVisible();
  });

  test("shows nav links for Activity and Manual Apply", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    await expect(page.getByText("Activity").first()).toBeVisible();
    await expect(page.getByText("Manual Apply").first()).toBeVisible();
  });

  test("shows session info sidebar", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Sidebar should show session metadata
    await expect(page.getByText("Session").first()).toBeVisible();
    // Keywords label (uppercase, no colon)
    await expect(page.getByText("Keywords").first()).toBeVisible();
    // Keywords shown as individual badges
    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Senior Engineer").first()).toBeVisible();
    // Application counters
    await expect(page.getByText("Applied").first()).toBeVisible();
    await expect(page.getByText("Submitted").first()).toBeVisible();
  });

  test("displays SSE events in the status feed", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Wait for SSE events to appear in the feed
    await expect(
      page.getByText("Pipeline started - discovering jobs")
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByText("Scanning Indeed for React jobs...")
    ).toBeVisible({ timeout: 10_000 });
  });

  test("dashboard link is present in session viewer nav", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    const dashboardLink = page.getByRole("link", { name: "Dashboard" });
    await expect(dashboardLink).toBeVisible();
  });
});
