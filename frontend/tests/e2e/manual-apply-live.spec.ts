// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";
const VERIFIED_SUBMITTED_SESSION_ID = "5ebabbc4-7efd-4165-aee0-3899a692a6eb";

test.describe("Manual Apply (Live Integration)", () => {
  test("manual-apply UI shows persisted submitted entry with cover letter and tailored resume", async ({
    page,
  }) => {
    test.setTimeout(60_000);

    await login(page);

    const logRes = await page.request.get(
      `${API_BASE}/api/sessions/${VERIFIED_SUBMITTED_SESSION_ID}/application-log`
    );
    expect(logRes.status()).toBe(200);

    const body = await logRes.json();
    const entries = (body.entries ?? []) as Array<{
      status?: string;
      job?: { title?: string; company?: string };
      cover_letter?: string;
      tailored_resume?: { tailored_text?: string } | null;
    }>;
    const submitted = entries.find(
      (entry) =>
        entry.status === "submitted" &&
        entry.job?.title === "Applied AI Engineer, Beneficial Deployments" &&
        entry.job?.company === "Anthropic"
    );

    expect(submitted).toBeTruthy();
    expect((submitted?.cover_letter ?? "").length).toBeGreaterThan(100);
    expect(
      (submitted?.tailored_resume?.tailored_text ?? "").length
    ).toBeGreaterThan(50);

    await page.goto(`/session/${VERIFIED_SUBMITTED_SESSION_ID}/manual-apply`);

    await expect(page.getByText("Application Log")).toBeVisible();
    await expect(
      page.getByText("Applied AI Engineer, Beneficial Deployments")
    ).toBeVisible({
      timeout: 20_000,
    });
    await expect(
      page.getByText("submitted", { exact: true }).first()
    ).toBeVisible();

    await page.getByText("Details").first().click();
    await expect(
      page.getByRole("heading", { name: "Cover Letter" })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Tailored Resume" })
    ).toBeVisible();

    const coverDownload = page.getByRole("button", {
      name: "Download PDF",
    }).first();
    const [coverLetterPdf] = await Promise.all([
      page.waitForEvent("download"),
      coverDownload.click(),
    ]);
    expect(coverLetterPdf.suggestedFilename()).toMatch(/\.pdf$/);

    const resumeDownload = page.getByRole("button", {
      name: "Download PDF",
    }).nth(1);
    const [resumePdf] = await Promise.all([
      page.waitForEvent("download"),
      resumeDownload.click(),
    ]);
    expect(resumePdf.suggestedFilename()).toMatch(/\.pdf$/);
  });
});
