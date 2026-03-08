// Copyright (c) 2026 V2 Software LLC. All rights reserved.

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
import path from "path";
import fs from "fs";

const API_BASE = "http://localhost:8000";
const RESUME_TEXT =
  "John Doe\nSenior Backend Engineer\nSan Francisco, CA\njohn@example.com\n\n" +
  "Experience:\n- 5 years Python, FastAPI, Django\n- AWS, Docker, Kubernetes\n" +
  "- PostgreSQL, Redis\n- CI/CD pipelines\n\nEducation:\nBS Computer Science, UC Berkeley";

// Helper: create a resume file and fill wizard to create a session
async function createSessionViaWizard(
  page: Page,
  resumeFilePath: string
): Promise<string> {
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

  // Step 2: Resume — upload file
  await page.locator("#resume-upload").setInputFiles(resumeFilePath);
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForTimeout(500);

  // Step 3: Review & Launch
  await expect(
    page.getByText("Review & Launch", { exact: true }).first()
  ).toBeVisible();
  await page.getByRole("button", { name: "Start Job Hunt Session" }).click();

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
  let resumeFilePath: string;

  test.beforeAll(() => {
    resumeFilePath = path.join(
      __dirname,
      "fixtures",
      "test-resume-pipeline.txt"
    );
    fs.mkdirSync(path.dirname(resumeFilePath), { recursive: true });
    fs.writeFileSync(resumeFilePath, RESUME_TEXT);
  });

  test.afterAll(() => {
    try {
      fs.unlinkSync(resumeFilePath);
    } catch {
      /* ignore */
    }
  });

  test.beforeEach(async ({ page, request }) => {
    const health = await request.get(`${API_BASE}/api/health`);
    expect(health.status()).toBe(200);
    await login(page);
  });

  test("wizard creates session and coaching events stream", async ({
    page,
  }) => {
    test.setTimeout(120_000);

    const sessionId = await createSessionViaWizard(page, resumeFilePath);
    expect(sessionId).toBeTruthy();

    // Verify session page loaded — main card is "Live Status"
    await expect(page.getByText("Live Status")).toBeVisible({
      timeout: 10_000,
    });

    // Verify SSE events start streaming (message from backend status event)
    await expect(
      page.getByText("Starting your job hunt session...")
    ).toBeVisible({
      timeout: 10_000,
    });

    // Wait for coaching to begin — look for Coach step label
    await expect(page.getByText(/coach/i).first()).toBeVisible({
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
    await expect(page.getByText("Live Status")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for coaching to complete and coach review modal to appear
    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible({ timeout: 120_000 });

    await page.screenshot({
      path: "test-results/pipeline-coach-review-modal.png",
    });

    // Click Approve button
    const approveBtn = dialog.getByRole("button", {
      name: /Approve|Continue/i,
    });
    await expect(approveBtn).toBeVisible({ timeout: 5_000 });
    await approveBtn.click();

    // Modal should close
    await expect(dialog).not.toBeVisible({ timeout: 10_000 });

    // Status should advance past coaching
    await expect(
      page.getByText(/discover|search|finding/i).first()
    ).toBeVisible({
      timeout: 30_000,
    });

    await page.screenshot({
      path: "test-results/pipeline-post-coach-approve.png",
    });
  });

  test("shortlist review shows max 20 jobs and approval works", async ({
    page,
  }) => {
    test.setTimeout(600_000);

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

    // Navigate to session page immediately
    await page.goto(`/session/${sessionId}`);
    await expect(page.getByText("Live Status")).toBeVisible({
      timeout: 10_000,
    });

    // Wait for coach review modal, approve it
    const coachDialog = page.getByRole("dialog").first();
    await expect(coachDialog).toBeVisible({ timeout: 120_000 });

    const coachApproveBtn = coachDialog.getByRole("button", {
      name: /Approve|Continue/i,
    });
    await expect(coachApproveBtn).toBeVisible({ timeout: 5_000 });
    await coachApproveBtn.click();
    await expect(coachDialog).not.toBeVisible({ timeout: 10_000 });

    // Wait for shortlist review dialog (after discovery + scoring + tailoring)
    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible({ timeout: 540_000 });

    await page.screenshot({
      path: "test-results/pipeline-shortlist-review.png",
    });

    // COUNT the job items — must be <= 20
    const jobItems = dialog.locator(
      '[data-testid="job-item"], tr, [class*="job"], [class*="Job"]'
    );
    const jobCount = await jobItems.count();

    let actualCount = jobCount;
    if (jobCount === 0) {
      const checkboxes = dialog.locator('input[type="checkbox"]');
      actualCount = await checkboxes.count();
    }

    console.log(`Shortlist job count in modal: ${actualCount}`);
    expect(actualCount).toBeLessThanOrEqual(20);
    expect(actualCount).toBeGreaterThan(0);

    // Approve the shortlist
    const approveBtn = dialog.getByRole("button", {
      name: /Approve|Apply|Submit|Continue/i,
    });
    await expect(approveBtn).toBeVisible({ timeout: 5_000 });

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
    // This path runs full live discovery/scoring and can exceed 5 minutes.
    test.setTimeout(600_000);

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

    // Poll until we reach awaiting_review, auto-approving coach review
    {
      const start = Date.now();
      let coachApproved = false;
      while (Date.now() - start < 540_000) {
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
