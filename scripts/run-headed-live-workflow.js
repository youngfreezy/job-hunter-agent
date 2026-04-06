#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { chromium } = require(path.join(
  __dirname,
  "..",
  "frontend",
  "node_modules",
  "playwright"
));

const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:3000";
const API_BASE = process.env.API_BASE || "http://localhost:8000";
const RESUME_PATH =
  process.env.RESUME_PATH ||
  "/path/to/your/resume.pdf";
const KEYWORDS =
  process.env.KEYWORDS ||
  "AI Engineer, Machine Learning Engineer, Software Engineer";
const LOCATION = process.env.LOCATION || "Remote";
const TARGET_SUBMISSIONS = Number(process.env.TARGET_SUBMISSIONS || "5");
const MAX_RUNTIME_MS = Number(process.env.MAX_RUNTIME_MS || 30 * 60 * 1000);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Request failed ${res.status}: ${url}`);
  }
  return res.json();
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`POST failed ${res.status}: ${url}`);
  }
  if (res.headers.get("content-type")?.includes("application/json")) {
    return res.json();
  }
  return null;
}

async function getApplicationLog(sessionId) {
  return fetchJson(`${API_BASE}/api/sessions/${sessionId}/application-log`);
}

async function getSession(sessionId) {
  return fetchJson(`${API_BASE}/api/sessions/${sessionId}`);
}

async function clickIfVisible(page, role, name) {
  const locator = page.getByRole(role, { name });
  if (await locator.isVisible().catch(() => false)) {
    await locator.click();
    return true;
  }
  return false;
}

async function clickByRegexIfVisible(page, role, name) {
  const locator = page.getByRole(role, { name });
  if (await locator.first().isVisible().catch(() => false)) {
    await locator.first().click();
    return true;
  }
  return false;
}

async function createSession(page) {
  console.log("Opening session wizard");
  await page.goto(`${FRONTEND_URL}/session/new`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "New Session" }).waitFor({
    timeout: 60000,
  });
  console.log("Filling keywords");
  await page.getByPlaceholder(
    "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
  ).fill(KEYWORDS);
  await page.getByText("Remote only").click();
  const locationInput = page.getByPlaceholder("e.g. San Francisco, Remote, Austin");
  if (await locationInput.isVisible().catch(() => false)) {
    console.log("Filling location");
    await locationInput.fill(LOCATION);
    await page.keyboard.press("Enter");
  }

  console.log("Moving to resume step");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Your Resume", { exact: true }).first().waitFor({
    timeout: 30000,
  });
  console.log("Uploading resume");
  await page.locator("#resume-upload").setInputFiles(RESUME_PATH);
  await page.getByText(path.basename(RESUME_PATH)).first().waitFor({
    timeout: 30000,
  });
  console.log("Moving to review step");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByText("Review & Launch", { exact: true }).first().waitFor({
    timeout: 30000,
  });
  console.log("Starting session");
  await page.getByRole("button", { name: "Start Job Hunt Session" }).click({
    timeout: 30000,
  });
  await page.waitForURL(/\/session\/[a-f0-9-]+/, { timeout: 120000 });
  const match = page.url().match(/\/session\/([a-f0-9-]+)/);
  if (!match) {
    throw new Error(`Failed to extract session id from ${page.url()}`);
  }
  return match[1];
}

async function verifyManualApplyPage(page, sessionId) {
  await page.goto(`${FRONTEND_URL}/session/${sessionId}/manual-apply`, {
    waitUntil: "domcontentloaded",
  });
  await page.getByText("Application Log").waitFor({ timeout: 60000 });
  await page.getByRole("button", { name: "Details" }).first().click();
  await page.getByRole("heading", { name: "Cover Letter" }).waitFor({
    timeout: 30000,
  });
  await page.getByRole("heading", { name: "Tailored Resume" }).waitFor({
    timeout: 30000,
  });

  const [coverDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download PDF" }).first().click(),
  ]);
  const [resumeDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download PDF" }).nth(1).click(),
  ]);

  return {
    coverLetterPdf: coverDownload.suggestedFilename(),
    tailoredResumePdf: resumeDownload.suggestedFilename(),
  };
}

async function monitorSession(page, sessionId) {
  const startedAt = Date.now();
  const manualActions = [];

  while (Date.now() - startedAt < MAX_RUNTIME_MS) {
    await page.goto(`${FRONTEND_URL}/session/${sessionId}`, {
      waitUntil: "domcontentloaded",
    });

    if (await clickIfVisible(page, "button", "Approve & Start Job Discovery")) {
      manualActions.push("coach-approved");
      await sleep(2000);
      continue;
    }

    if (await clickByRegexIfVisible(page, "button", /Apply to \d+ Jobs/)) {
      manualActions.push("shortlist-approved");
      await sleep(2000);
      continue;
    }

    if (await clickIfVisible(page, "button", "Submit Application")) {
      manualActions.push("submit-confirmed");
      await sleep(2000);
      continue;
    }

    if (await clickIfVisible(page, "button", "Resume Agent")) {
      manualActions.push("resumed-agent");
      await sleep(2000);
      continue;
    }

    if (
      await clickByRegexIfVisible(page, "button", /I've Logged In.*Continue/)
    ) {
      manualActions.push("confirmed-login");
      await sleep(2000);
      continue;
    }

    const [session, log] = await Promise.all([
      getSession(sessionId),
      getApplicationLog(sessionId),
    ]);

    if (session.status === "awaiting_coach_review") {
      await postJson(`${API_BASE}/api/sessions/${sessionId}/coach-review`, {
        approved: true,
      });
      manualActions.push("coach-approved-api");
      await sleep(2000);
      continue;
    }

    if (session.status === "awaiting_review") {
      const approvedJobIds = (session.scored_jobs || []).map((item) => item.job.id);
      await postJson(`${API_BASE}/api/sessions/${sessionId}/review`, {
        approved_job_ids: approvedJobIds,
        feedback: "",
      });
      manualActions.push(`shortlist-approved-api:${approvedJobIds.length}`);
      await sleep(2000);
      continue;
    }
    const entries = log.entries || [];
    const submittedEntries = entries.filter((entry) => entry.status === "submitted");
    const failedEntries = entries.filter((entry) => entry.status === "failed");
    const skippedEntries = entries.filter((entry) => entry.status === "skipped");

    console.log(
      JSON.stringify(
        {
          sessionId,
          status: session.status,
          submitted: submittedEntries.length,
          failed: failedEntries.length,
          skipped: skippedEntries.length,
          manualActions,
        },
        null,
        2
      )
    );

    if (submittedEntries.length >= TARGET_SUBMISSIONS) {
      return {
        session,
        entries,
        manualActions,
      };
    }

    if (session.status === "completed" || session.status === "failed") {
      return {
        session,
        entries,
        manualActions,
      };
    }

    await sleep(10000);
  }

  const [session, log] = await Promise.all([
    getSession(sessionId),
    getApplicationLog(sessionId),
  ]);
  return {
    session,
    entries: log.entries || [],
    manualActions,
  };
}

async function main() {
  if (!fs.existsSync(RESUME_PATH)) {
    throw new Error(`Resume file not found: ${RESUME_PATH}`);
  }

  console.log(`Using resume: ${RESUME_PATH}`);
  const browser = await chromium.launch({
    headless: false,
    slowMo: 100,
  });
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport: { width: 1440, height: 1100 },
  });
  await context.addCookies([
    {
      name: "jobhunter_test_bypass",
      value: "1",
      domain: "localhost",
      path: "/",
      httpOnly: false,
      sameSite: "Lax",
    },
  ]);

  const page = await context.newPage();
  console.log("Browser launched");
  const sessionId = await createSession(page);
  console.log(`Created session ${sessionId}`);

  const result = await monitorSession(page, sessionId);
  const submittedEntries = result.entries.filter((entry) => entry.status === "submitted");

  let manualArtifacts = null;
  if (result.entries.length > 0) {
    manualArtifacts = await verifyManualApplyPage(page, sessionId);
  }

  const summary = {
    sessionId,
    status: result.session.status,
    submitted: submittedEntries.length,
    failed: result.entries.filter((entry) => entry.status === "failed").length,
    skipped: result.entries.filter((entry) => entry.status === "skipped").length,
    manualActions: result.manualActions,
    manualArtifacts,
    firstSubmittedJob: submittedEntries[0]?.job || null,
  };

  const outputPath = path.join(
    __dirname,
    "..",
    "screenshots",
    "ux-audit",
    "latest-live-workflow-summary.json"
  );
  fs.writeFileSync(outputPath, JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));

  if (submittedEntries.length < TARGET_SUBMISSIONS) {
    throw new Error(
      `Expected at least ${TARGET_SUBMISSIONS} submitted jobs, got ${submittedEntries.length}`
    );
  }

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
