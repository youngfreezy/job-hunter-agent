// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";
const RESUME_TEXT =
  "Senior Software Engineer with 8 years of experience in React, Python, and cloud infrastructure.";
const RESUME_FILE = {
  name: "test-resume.txt",
  mimeType: "text/plain",
  buffer: Buffer.from(RESUME_TEXT),
};

test.describe("Session Creation - Multi-Step Wizard", () => {

  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/session/new");
    await expect(page).toHaveURL(/\/session\/new/);
  });

  // -- Step progress indicator --

  test("shows step progress indicator with 3 steps", async ({ page }) => {
    await expect(page.getByText("Job Search", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Resume & Profile", { exact: true })
    ).toBeVisible();
    await expect(
      page.getByText("Review & Launch", { exact: true })
    ).toBeVisible();
  });

  test("page header and description are visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "New Session" })
    ).toBeVisible();
    await expect(page.getByText("Configure the search once.")).toBeVisible();
  });

  // -- Step 1: Job Search --

  test("Step 1: shows keywords and location fields", async ({ page }) => {
    await expect(page.getByText("Search Keywords")).toBeVisible();
    await expect(page.getByText("Location & Preferences")).toBeVisible();
    await expect(
      page.getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
    ).toBeVisible();
    await expect(page.getByText("Remote only")).toBeVisible();
    await expect(page.getByPlaceholder("e.g. 120000")).toBeVisible();
    await expect(page.getByRole("button", { name: "Next" })).toBeVisible();
  });

  test("Step 1: keywords input shows live Badge preview", async ({ page }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React, Python, Machine Learning");

    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Python").first()).toBeVisible();
    await expect(page.getByText("Machine Learning")).toBeVisible();
  });

  test("Step 1: validation prevents advancing without keywords", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Enter at least one keyword.")).toBeVisible();
    await expect(page.getByText("Search Keywords")).toBeVisible();
  });

  test("Step 1: salary validation rejects negative values", async ({
    page,
  }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByPlaceholder("e.g. 120000").fill("-5000");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(
      page.getByText("Salary must be a positive number.")
    ).toBeVisible();
  });

  // -- Step 1 → Step 2 navigation --

  test("Step 1 -> Step 2: can advance with valid keywords", async ({
    page,
  }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React, Python");
    await page.getByRole("button", { name: "Next" }).click();
    // Should now see Step 2 content
    await expect(page.getByText("Your Resume", { exact: true })).toBeVisible();
    // File upload area should be visible
    await expect(page.getByText("Click to upload")).toBeVisible();
  });

  // -- Step 2: Resume & Profile --

  test("Step 2: validation prevents advancing without resume", async ({
    page,
  }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Try to advance without resume — should stay on Step 2
    await page.getByRole("button", { name: "Next" }).click();
    // Should still be on Step 2 (Your Resume card still visible)
    await expect(page.getByText("Your Resume", { exact: true })).toBeVisible();
    // Should NOT have advanced to Step 3 (Start button not visible)
    await expect(
      page.getByRole("button", { name: "Start Job Hunt Session" })
    ).not.toBeVisible();
  });

  test("Step 2: LinkedIn URL validation rejects invalid URLs", async ({
    page,
  }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Upload resume file
    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();

    await page
      .getByPlaceholder("https://linkedin.com/in/yourprofile")
      .fill("not-a-url");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText(/valid LinkedIn URL/)).toBeVisible();
  });

  test("Step 2: accepts valid LinkedIn URL", async ({ page }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Upload resume file
    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();

    await page
      .getByPlaceholder("https://linkedin.com/in/yourprofile")
      .fill("https://linkedin.com/in/testuser");
    await page.getByRole("button", { name: "Next" }).click();

    // Should advance to Step 3
    await expect(
      page.getByRole("button", { name: "Start Job Hunt Session" })
    ).toBeVisible();
  });

  // -- Step 3: Review & Launch --

  test("Step 3: shows review summary with keywords and resume preview", async ({
    page,
  }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React, Python");
    await page
      .getByPlaceholder("e.g. San Francisco, New York, Austin")
      .fill("San Francisco");
    await page.getByText("Remote only").click();
    await page.getByPlaceholder("e.g. 120000").fill("150000");
    await page.getByRole("button", { name: "Next" }).click();

    // Upload resume file
    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: verify review content
    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Python").first()).toBeVisible();
    await expect(page.getByText("San Francisco")).toBeVisible();
    await expect(page.getByText("Remote only")).toBeVisible();
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Start Job Hunt Session" })
    ).toBeVisible();
  });

  test("Step 3: edit buttons navigate back to correct steps", async ({
    page,
  }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();

    // Click "Edit" on Job Search section
    await page.getByRole("button", { name: /Edit/ }).first().click();

    // Should be back on Step 1
    await expect(page.getByText("Search Keywords")).toBeVisible();
    await expect(
      page.getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
    ).toHaveValue("React");
  });

  // -- Navigation --

  test("Back button navigates to previous step", async ({ page }) => {
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Your Resume", { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Back" }).click();
    await expect(page.getByText("Search Keywords")).toBeVisible();
  });

  test("Back button is disabled on Step 1", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Back" })).toBeDisabled();
  });

  // -- localStorage persistence --

  test("localStorage persistence: data survives page refresh", async ({
    page,
  }) => {
    const keywordsInput = page.getByPlaceholder(
      "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
    );
    await keywordsInput.fill("React, Python");

    await page.waitForTimeout(500);
    await page.reload();

    await expect(keywordsInput).toHaveValue("React, Python");
  });

  // -- Full flow submission --

  test("full wizard: fill all steps and submit successfully", async ({
    page,
  }) => {
    const mockSessionId = "test-session-abc123";
    await page.route("**/api/sessions", async (route) => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        expect(body.keywords).toContain("React");
        expect(body.resume_text).toBeTruthy();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ session_id: mockSessionId }),
        });
      } else {
        await route.continue();
      }
    });

    // Step 1
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React, Python");
    await page
      .getByPlaceholder("e.g. San Francisco, New York, Austin")
      .fill("San Francisco");
    await page.getByText("Remote only").click();
    await page.getByPlaceholder("e.g. 120000").fill("150000");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2
    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: Submit
    await page.getByRole("button", { name: "Start Job Hunt Session" }).click();

    await page.waitForURL(`**/session/${mockSessionId}`, { timeout: 10_000 });
  });

  test("shows error message when session creation fails", async ({ page }) => {
    await page.route("**/api/sessions", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Internal server error" }),
        });
      } else {
        await route.continue();
      }
    });

    // Step 1
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2
    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: Submit
    await page.getByRole("button", { name: "Start Job Hunt Session" }).click();

    await expect(
      page.getByText(
        /Failed to start session|Internal server error|Unable to connect/
      )
    ).toBeVisible();
  });

  test("shows loading state while submitting", async ({ page }) => {
    await page.route("**/api/sessions", async (route) => {
      if (route.request().method() === "POST") {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ session_id: "loading-test-id" }),
        });
      } else {
        await route.continue();
      }
    });

    // Step 1
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2
    await page.locator("#resume-upload").setInputFiles(RESUME_FILE);
    await expect(page.getByText("test-resume.txt").first()).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: Submit — click the launch button
    await page.getByRole("button", { name: "Start Job Hunt Session" }).click();

    // While loading, the button text is replaced by animated dots (LoadingDots)
    // and the button is disabled. The text "Start Job Hunt Session" disappears.
    await expect(
      page.getByRole("button", { name: "Start Job Hunt Session" })
    ).not.toBeVisible({ timeout: 3_000 });
  });
});
