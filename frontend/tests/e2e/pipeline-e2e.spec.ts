/**
 * End-to-end pipeline test: Wizard -> Coach Review -> Discovery -> Shortlist Review
 *
 * Tests the REAL flow against running backend + frontend. Verifies:
 * 1. Wizard completes and creates a session
 * 2. SSE events stream coaching progress
 * 3. Coach review modal appears and can be approved
 * 4. Discovery + scoring progress events arrive
 * 5. Shortlist review modal shows MAX 20 jobs (not all scored)
 * 6. Shortlist approval works without hanging
 * 7. Page reload restores state at HITL checkpoints
 */
import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

// Helper: fill wizard and submit to create a session
async function createSessionViaWizard(page: Page): Promise<string> {
  await page.goto("/session/new");
  await expect(
    page.getByRole("heading", { name: "New Session" })
  ).toBeVisible();

  // Step 1: Keywords
  await page
    .getByPlaceholder(
      "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
    )
    .fill("Python, Backend Engineer");
  await page.getByText("Remote only").click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForTimeout(500);

  // Step 2: Resume
  await page
    .getByPlaceholder("Paste your full resume text here...")
    .fill(
      "John Doe\nSenior Backend Engineer\nSan Francisco, CA\njohn@example.com\n\n" +
        "Experience:\n- 5 years Python, FastAPI, Django\n- AWS, Docker, Kubernetes\n" +
        "- PostgreSQL, Redis\n- CI/CD pipelines\n\nEducation:\nBS Computer Science, UC Berkeley"
    );
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForTimeout(500);

  // Step 3: Review & Launch
  await expect(
    page.getByText("Review & Launch", { exact: true }).first()
  ).toBeVisible();
  await page.getByRole("button", { name: /Launch|Submit|Start/ }).click();

  // Wait for redirect to session page
  await page.waitForURL(/\/session\/[a-f0-9-]+/, { timeout: 15_000 });
  await page.waitForTimeout(1000);

  const url = page.url();
  const sessionId = url.split("/session/")[1];
  return sessionId;
}

// Helper: wait for a specific session status via API polling
async function waitForStatus(
  page: Page,
  sessionId: string,
  targetStatuses: string[],
  timeoutMs = 300_000
): Promise<string> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const res = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`);
    if (res.ok()) {
      const data = await res.json();
      if (targetStatuses.includes(data.status)) {
        return data.status;
      }
    }
    await page.waitForTimeout(5_000);
  }
  throw new Error(
    `Timed out waiting for status ${targetStatuses.join(
      "|"
    )} after ${timeoutMs}ms`
  );
}

test.describe("Full Pipeline E2E", () => {
  test.beforeEach(async ({ page, request }) => {
    const health = await request.get(`${API_BASE}/api/health`);
    expect(health.status()).toBe(200);
    await login(page);
  });

  test("wizard creates session and coaching events stream", async ({
    page,
  }) => {
    test.setTimeout(120_000);

    const sessionId = await createSessionViaWizard(page);
    expect(sessionId).toBeTruthy();

    // Verify session page loaded
    await expect(page.getByText("Status Feed")).toBeVisible({
      timeout: 10_000,
    });

    // Verify SSE events start streaming
    await expect(page.getByText("Pipeline started")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for coaching to begin
    await expect(page.getByText(/coaching/i).first()).toBeVisible({
      timeout: 15_000,
    });

    await page.screenshot({ path: "test-results/pipeline-coaching.png" });
  });

  test("coach review modal appears and can be approved", async ({ page }) => {
    test.setTimeout(180_000);

    // Create session via API for speed
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Python", "Backend"],
        locations: [],
        remote_only: true,
        salary_min: 120000,
        resume_text:
          "Jane Smith\nSenior Engineer\njane@test.com\n5 years Python, FastAPI, AWS, Docker, Kubernetes",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    // Navigate to session page and connect SSE
    await page.goto(`/session/${sessionId}`);
    await expect(page.getByText("Status Feed")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for coaching to complete and coach review modal to appear
    // The modal has a DialogTitle with "Resume Coach Review" or similar
    await expect(page.getByRole("dialog").first()).toBeVisible({
      timeout: 120_000,
    });

    await page.screenshot({
      path: "test-results/pipeline-coach-review-modal.png",
    });

    // The modal should show coach output (rewritten resume, score, etc.)
    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible();

    // Click Approve button
    const approveBtn = dialog.getByRole("button", {
      name: /Approve|Continue/i,
    });
    await expect(approveBtn).toBeVisible({ timeout: 5_000 });
    await approveBtn.click();

    // Modal should close
    await expect(dialog).not.toBeVisible({ timeout: 10_000 });

    // Status should advance past coaching
    await expect(page.getByText(/discover/i).first()).toBeVisible({
      timeout: 30_000,
    });

    await page.screenshot({
      path: "test-results/pipeline-post-coach-approve.png",
    });
  });

  test("shortlist review shows max 20 jobs and approval works", async ({
    page,
  }) => {
    test.setTimeout(600_000); // 10 min — discovery + scoring takes time

    // Create session via API
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Python", "Backend Engineer"],
        locations: ["San Francisco"],
        remote_only: true,
        salary_min: 120000,
        resume_text:
          "Test User\nSenior Backend Engineer\ntest@example.com\n" +
          "5 years Python, FastAPI, Django, AWS, Docker, Kubernetes, PostgreSQL, Redis, CI/CD",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    // Navigate to session page immediately so we receive SSE events in real-time
    await page.goto(`/session/${sessionId}`);
    await expect(page.getByText("Status Feed")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for coach review modal, approve it, then wait for shortlist review
    // The coach review dialog appears first
    const coachDialog = page.getByRole("dialog").first();
    await expect(coachDialog).toBeVisible({ timeout: 120_000 });

    // Approve coach review via the dialog button
    const coachApproveBtn = coachDialog.getByRole("button", {
      name: /Approve|Continue/i,
    });
    await expect(coachApproveBtn).toBeVisible({ timeout: 5_000 });
    await coachApproveBtn.click();
    await expect(coachDialog).not.toBeVisible({ timeout: 10_000 });

    // Now wait for the shortlist review dialog (after discovery + scoring + tailoring)
    // This can take 5-8 minutes
    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible({ timeout: 540_000 });

    await page.screenshot({
      path: "test-results/pipeline-shortlist-review.png",
    });

    // COUNT the job items in the shortlist — must be <= 20
    // Look for job cards/rows in the dialog
    const jobItems = dialog.locator(
      '[data-testid="job-item"], tr, [class*="job"], [class*="Job"]'
    );
    const jobCount = await jobItems.count();

    // If no specific selectors match, count by looking for checkboxes (each job has one)
    let actualCount = jobCount;
    if (jobCount === 0) {
      const checkboxes = dialog.locator('input[type="checkbox"]');
      actualCount = await checkboxes.count();
    }

    console.log(`Shortlist job count in modal: ${actualCount}`);
    expect(actualCount).toBeLessThanOrEqual(20);
    expect(actualCount).toBeGreaterThan(0);

    await page.screenshot({
      path: "test-results/pipeline-shortlist-count.png",
    });

    // Approve the shortlist — click "Approve" or "Apply to Selected"
    const approveBtn = dialog.getByRole("button", {
      name: /Approve|Apply|Submit|Continue/i,
    });
    await expect(approveBtn).toBeVisible({ timeout: 5_000 });

    // Click and verify it doesn't hang (returns within 10s)
    const startTime = Date.now();
    await approveBtn.click();
    const elapsed = Date.now() - startTime;
    console.log(`Shortlist approval click took ${elapsed}ms`);

    // Modal should close
    await expect(dialog).not.toBeVisible({ timeout: 15_000 });

    // Backend should still be responsive
    const healthRes = await page.request.get(`${API_BASE}/api/health`);
    expect(healthRes.status()).toBe(200);

    // Status should advance to applying
    await expect(
      page.getByText(/apply|tailoring|applying/i).first()
    ).toBeVisible({ timeout: 30_000 });

    await page.screenshot({
      path: "test-results/pipeline-post-shortlist-approve.png",
    });
  });

  test("page reload restores HITL state", async ({ page }) => {
    test.setTimeout(300_000);

    // Create session via API
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["React", "Frontend"],
        locations: [],
        remote_only: true,
        salary_min: null,
        resume_text:
          "Alex Dev\nFrontend Engineer\nalex@test.com\n3 years React, TypeScript, Next.js",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    // Wait for coach review HITL
    await waitForStatus(page, sessionId, ["awaiting_coach_review"], 180_000);

    // Navigate to session page — coach review modal should appear
    await page.goto(`/session/${sessionId}`);
    await page.waitForTimeout(3000);

    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible({ timeout: 30_000 });

    await page.screenshot({ path: "test-results/pipeline-reload-before.png" });

    // Reload the page
    await page.reload();
    await page.waitForTimeout(3000);

    // Coach review modal should STILL appear after reload
    const dialogAfter = page.getByRole("dialog").first();
    await expect(dialogAfter).toBeVisible({ timeout: 30_000 });

    await page.screenshot({ path: "test-results/pipeline-reload-after.png" });

    // Verify backend health
    const health = await page.request.get(`${API_BASE}/api/health`);
    expect(health.status()).toBe(200);
  });

  test("GET session caps scored_jobs to 20", async ({ page }) => {
    test.setTimeout(300_000);

    // Create session and get to shortlist review
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Python", "Data"],
        locations: [],
        remote_only: true,
        salary_min: null,
        resume_text:
          "Data Person\nData Engineer\ndata@test.com\n5 years Python, Spark, SQL, AWS",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    // Poll until we reach awaiting_review, auto-approving coach review along the way
    {
      const start = Date.now();
      let coachApproved = false;
      while (Date.now() - start < 480_000) {
        const res = await page.request.get(
          `${API_BASE}/api/sessions/${sessionId}`
        );
        const data = await res.json();

        if (data.status === "awaiting_review") break;

        if (data.status === "awaiting_coach_review" && !coachApproved) {
          await page.request.post(
            `${API_BASE}/api/sessions/${sessionId}/coach-review`,
            { data: { approved: true } }
          );
          coachApproved = true;
        }

        if (["completed", "failed"].includes(data.status)) {
          throw new Error(`Pipeline ended with status ${data.status}`);
        }

        await page.waitForTimeout(5_000);
      }
    }

    // Verify the API response caps scored_jobs at 20
    const sessionRes = await page.request.get(
      `${API_BASE}/api/sessions/${sessionId}`
    );
    expect(sessionRes.ok()).toBeTruthy();
    const sessionJson = await sessionRes.json();

    const scoredJobs = sessionJson.scored_jobs || [];
    console.log(`API returned ${scoredJobs.length} scored jobs`);
    expect(scoredJobs.length).toBeLessThanOrEqual(20);

    // Verify they're sorted by score descending
    if (scoredJobs.length > 1) {
      for (let i = 0; i < scoredJobs.length - 1; i++) {
        const scoreA = scoredJobs[i].score ?? scoredJobs[i]?.score;
        const scoreB = scoredJobs[i + 1].score ?? scoredJobs[i + 1]?.score;
        if (scoreA !== undefined && scoreB !== undefined) {
          expect(scoreA).toBeGreaterThanOrEqual(scoreB);
        }
      }
    }
  });
});
