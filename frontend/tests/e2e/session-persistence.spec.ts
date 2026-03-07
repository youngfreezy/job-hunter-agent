import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

test.describe("Session Persistence and Dashboard", () => {
  // -- API connectivity --

  test("GET /api/sessions returns a list", async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/sessions`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body)).toBeTruthy();
  });

  // -- Dashboard --

  test("dashboard fetches and displays sessions from API", async ({ page }) => {
    await login(page);

    await page.route("**/api/sessions", async (route) => {
      if (
        route.request().method() === "GET" &&
        !route.request().url().includes("/api/sessions/")
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              session_id: "test-session-1",
              status: "completed",
              keywords: ["React", "Python"],
              locations: ["Remote"],
              remote_only: true,
              salary_min: null,
              resume_text_snippet: "Senior engineer...",
              linkedin_url: null,
              applications_submitted: 5,
              applications_failed: 1,
              created_at: "2026-03-04T12:00:00Z",
            },
          ]),
        });
      } else {
        await route.continue();
      }
    });

    await page.goto("/dashboard");

    await expect(page.getByText("No sessions yet")).not.toBeVisible();
    await expect(page.getByText("React, Python")).toBeVisible();
    // STATUS_LABELS maps "completed" → "Completed"
    await expect(page.getByText("Completed").first()).toBeVisible();
  });

  test("dashboard shows empty state when no sessions", async ({ page }) => {
    await login(page);

    await page.route("**/api/sessions", async (route) => {
      if (
        route.request().method() === "GET" &&
        !route.request().url().includes("/api/sessions/")
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      } else {
        await route.continue();
      }
    });

    await page.goto("/dashboard");
    await expect(page.getByText("No sessions yet")).toBeVisible();
  });

  test("dashboard session card links to session page", async ({ page }) => {
    await login(page);

    await page.route("**/api/sessions", async (route) => {
      if (
        route.request().method() === "GET" &&
        !route.request().url().includes("/api/sessions/")
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              session_id: "nav-test-001",
              status: "applying",
              keywords: ["DevOps"],
              locations: ["Remote"],
              remote_only: true,
              salary_min: null,
              resume_text_snippet: "",
              linkedin_url: null,
              applications_submitted: 2,
              applications_failed: 0,
              created_at: "2026-03-04T10:00:00Z",
            },
          ]),
        });
      } else {
        await route.continue();
      }
    });

    await page.goto("/dashboard");
    // The card is a Link wrapping the whole card, keyword text inside
    const sessionLink = page.locator('a[href="/session/nav-test-001"]');
    await expect(sessionLink).toBeVisible();
    await expect(page.getByText("DevOps")).toBeVisible();
  });

  test("dashboard stats reflect session data", async ({ page }) => {
    await login(page);

    await page.route("**/api/sessions", async (route) => {
      if (
        route.request().method() === "GET" &&
        !route.request().url().includes("/api/sessions/")
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              session_id: "s1",
              status: "completed",
              keywords: ["ML"],
              locations: [],
              remote_only: false,
              salary_min: null,
              resume_text_snippet: "",
              linkedin_url: null,
              applications_submitted: 3,
              applications_failed: 0,
              created_at: "2026-03-04T09:00:00Z",
            },
            {
              session_id: "s2",
              status: "applying",
              keywords: ["React"],
              locations: [],
              remote_only: false,
              salary_min: null,
              resume_text_snippet: "",
              linkedin_url: null,
              applications_submitted: 2,
              applications_failed: 1,
              created_at: "2026-03-04T10:00:00Z",
            },
          ]),
        });
      } else {
        await route.continue();
      }
    });

    await page.goto("/dashboard");

    // Total Sessions = 2
    await expect(
      page.locator("text=Total Sessions").locator("..").getByText("2")
    ).toBeVisible();
    // Applications Sent = 5 (3 + 2)
    await expect(
      page.locator("text=Applications Sent").locator("..").getByText("5")
    ).toBeVisible();
    // Completed = 1 — use first() since "Completed" appears in stats label + badge
    await expect(
      page.locator("text=Completed").locator("..").getByText("1").first()
    ).toBeVisible();
  });

  // -- Session page keywords from registry --

  test("session page shows keywords from getSession registry fallback", async ({
    page,
  }) => {
    await login(page);
    const mockId = "persist-test-001";

    await page.route(`**/api/sessions/${mockId}`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: mockId,
            status: "discovering",
            keywords: ["Machine Learning", "Data Scientist"],
            locations: ["San Francisco"],
            remote_only: false,
            scored_jobs: [],
            applications_submitted: [],
            applications_failed: [],
            steering_mode: "status",
            applications_used: 0,
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Mock SSE stream
    await page.route(`**/api/sessions/${mockId}/stream`, async (route) => {
      const body = [
        `event: status\ndata: ${JSON.stringify({
          status: "discovering",
          message: "Scanning job boards...",
          keywords: ["Machine Learning", "Data Scientist"],
        })}\n\n`,
      ].join("");

      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
        },
        body,
      });
    });

    await page.goto(`/session/${mockId}`);

    // Keywords are shown as individual badges in the sidebar
    await expect(page.getByText("Machine Learning").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("Data Scientist").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  // -- SSE replay on refresh --

  test("session page refresh preserves events via SSE replay", async ({
    page,
  }) => {
    await login(page);
    const mockId = "replay-test-001";

    await page.route(`**/api/sessions/${mockId}`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            session_id: mockId,
            status: "scoring",
            keywords: ["React"],
            scored_jobs: [],
            applications_submitted: [],
            applications_failed: [],
            steering_mode: "status",
            applications_used: 0,
          }),
        });
      } else {
        await route.continue();
      }
    });

    await page.route(`**/api/sessions/${mockId}/stream`, async (route) => {
      const body = [
        `event: status\ndata: ${JSON.stringify({
          status: "intake",
          message: "Pipeline started",
          keywords: ["React"],
          timestamp: "2026-03-04T12:00:00Z",
        })}\n\n`,
        `event: status\ndata: ${JSON.stringify({
          status: "coaching",
          agent_statuses: {},
          timestamp: "2026-03-04T12:00:01Z",
        })}\n\n`,
        `event: discovery\ndata: ${JSON.stringify({
          status: "discovering",
          jobs_found: 15,
          timestamp: "2026-03-04T12:00:05Z",
        })}\n\n`,
        `event: scoring\ndata: ${JSON.stringify({
          status: "scoring",
          scored_count: 10,
          timestamp: "2026-03-04T12:00:10Z",
        })}\n\n`,
      ].join("");

      await route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
        },
        body,
      });
    });

    // First load
    await page.goto(`/session/${mockId}`);
    await expect(page.getByText("Pipeline started")).toBeVisible({
      timeout: 10_000,
    });

    // Refresh
    await page.reload();

    // After refresh, replayed events should still appear
    await expect(page.getByText("Pipeline started")).toBeVisible({
      timeout: 10_000,
    });
    // Discovery event renders as "Found 15 matching jobs"
    await expect(page.getByText(/Found 15/)).toBeVisible({
      timeout: 10_000,
    });
    // Scoring event renders as "Ranked 10 jobs by fit"
    await expect(page.getByText(/Ranked 10/)).toBeVisible({
      timeout: 10_000,
    });
  });
});
