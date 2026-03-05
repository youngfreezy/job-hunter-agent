import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

test.describe("Live Session Viewer", () => {
  const mockSessionId = "viewer-test-session-001";

  test.beforeEach(async ({ page }) => {
    // Log in first
    await login(page);

    // Mock the GET /api/sessions/:id endpoint to return session data
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
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Mock the SSE stream endpoint to avoid hanging connections
    await page.route(
      `**/api/sessions/${mockSessionId}/stream`,
      async (route) => {
        // Return an SSE stream with a couple of mock events, then keep alive
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

    // Mock WebSocket connections to avoid errors
    // (Playwright handles this via page.route for HTTP-based connections)
  });

  test("session page loads and shows session data", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Should show JobHunter Agent branding
    await expect(page.getByText("JobHunter Agent").first()).toBeVisible();

    // Should show session status badge
    await expect(
      page.getByText("Discovering Jobs", { exact: true })
    ).toBeVisible();
  });

  test("shows pipeline progress steps", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // The progress bar and step indicators should be visible
    await expect(page.getByText(/Step \d+\/\d+/)).toBeVisible();

    // Should show pipeline step labels
    await expect(page.getByText("Intake")).toBeVisible();
    await expect(page.getByText("Coaching")).toBeVisible();
    await expect(page.getByText("Discovering", { exact: true })).toBeVisible();
    await expect(page.getByText("Scoring")).toBeVisible();
  });

  test("shows the Status Feed tab", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // The Status Feed tab should be visible and active by default
    await expect(page.getByText("Status Feed")).toBeVisible();
    await expect(page.getByText("Live Status")).toBeVisible();
  });

  test("shows all three viewer tabs", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    await expect(page.getByText("Status Feed")).toBeVisible();
    await expect(page.getByText("Screenshot Feed")).toBeVisible();
    await expect(page.getByText("Take Control")).toBeVisible();
  });

  test("shows session info sidebar", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Sidebar should show session metadata
    await expect(page.getByText("Session").first()).toBeVisible();
    await expect(page.getByText("Keywords:")).toBeVisible();
    await expect(page.getByText("React, Senior Engineer")).toBeVisible();
    await expect(page.getByText("Applications:")).toBeVisible();
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

  test("can switch to Screenshot Feed tab", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Click on Screenshot Feed tab
    await page.getByText("Screenshot Feed").click();

    // Should show the screenshot feed content area
    await expect(page.getByText("Live Screenshot Feed")).toBeVisible();
    await expect(
      page.getByText("Connecting to browser session...")
    ).toBeVisible();
  });

  test("can switch to Take Control tab", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Click on Take Control tab
    await page.getByText("Take Control").click();

    // Should show the browser control area
    await expect(page.getByText("Browser Control (noVNC)")).toBeVisible();
    await expect(page.getByText("Direct Browser Control")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Request Control" })
    ).toBeVisible();
  });

  test("shows chat panel in screenshot mode", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    // Switch to Screenshot Feed
    await page.getByText("Screenshot Feed").click();

    // Chat panel should appear
    await expect(page.getByPlaceholder(/Steer the agent/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
  });

  test("dashboard link is present in session viewer nav", async ({ page }) => {
    await page.goto(`/session/${mockSessionId}`);

    const dashboardLink = page.getByRole("link", { name: "Dashboard" });
    await expect(dashboardLink).toBeVisible();
  });
});
