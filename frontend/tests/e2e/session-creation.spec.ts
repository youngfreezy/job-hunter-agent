import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

test.describe("Session Creation - Multi-Step Wizard", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/session/new");
    await expect(page).toHaveURL(/\/session\/new/);
  });

  // -- Step progress indicator --

  test("shows step progress indicator with 3 steps", async ({ page }) => {
    await expect(page.getByText("Job Search", { exact: true })).toBeVisible();
    await expect(page.getByText("Resume & Profile", { exact: true })).toBeVisible();
    await expect(page.getByText("Review & Launch", { exact: true })).toBeVisible();
  });

  test("page header and description are visible", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "New Session" })
    ).toBeVisible();
    await expect(
      page.getByText("Configure your job search.")
    ).toBeVisible();
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
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React, Python, Machine Learning");

    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Python")).toBeVisible();
    await expect(page.getByText("Machine Learning")).toBeVisible();
  });

  test("Step 1: validation prevents advancing without keywords", async ({
    page,
  }) => {
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Enter at least one keyword.")).toBeVisible();
    // Should still be on Step 1
    await expect(page.getByText("Search Keywords")).toBeVisible();
  });

  test("Step 1: salary validation rejects negative values", async ({ page }) => {
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByPlaceholder("e.g. 120000").fill("-5000");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Salary must be a positive number.")).toBeVisible();
  });

  // -- Step 1 → Step 2 navigation --

  test("Step 1 -> Step 2: can advance with valid keywords", async ({ page }) => {
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React, Python");
    await page.getByRole("button", { name: "Next" }).click();
    // Should now see Step 2 content
    await expect(page.getByText("Your Resume", { exact: true })).toBeVisible();
    await expect(
      page.getByPlaceholder("Paste your full resume text here...")
    ).toBeVisible();
  });

  // -- Step 2: Resume & Profile --

  test("Step 2: validation prevents advancing without resume", async ({
    page,
  }) => {
    // Navigate to step 2
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Try to advance without resume
    await page.getByRole("button", { name: "Next" }).click();
    await expect(
      page.getByText("Upload a resume file or paste your resume text.").first()
    ).toBeVisible();
  });

  test("Step 2: LinkedIn URL validation rejects invalid URLs", async ({
    page,
  }) => {
    // Navigate to step 2
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Fill resume and invalid LinkedIn URL
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("My resume text");
    await page
      .getByPlaceholder("https://linkedin.com/in/yourprofile")
      .fill("not-a-url");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText(/valid LinkedIn URL/)).toBeVisible();
  });

  test("Step 2: accepts valid LinkedIn URL", async ({ page }) => {
    // Navigate to step 2
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Fill resume and valid LinkedIn URL
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("My resume text");
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
    // Fill step 1
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React, Python");
    await page
      .getByPlaceholder("e.g. San Francisco, New York, Austin")
      .fill("San Francisco");
    await page.getByText("Remote only").click();
    await page.getByPlaceholder("e.g. 120000").fill("150000");
    await page.getByRole("button", { name: "Next" }).click();

    // Fill step 2
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("Senior Engineer with 8 years of experience");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: verify review content
    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Python")).toBeVisible();
    await expect(page.getByText("San Francisco")).toBeVisible();
    await expect(page.getByText("Remote only")).toBeVisible();
    await expect(page.getByText("Senior Engineer with 8 years")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Start Job Hunt Session" })
    ).toBeVisible();
  });

  test("Step 3: edit buttons navigate back to correct steps", async ({
    page,
  }) => {
    // Fill step 1
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Fill step 2
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("My resume");
    await page.getByRole("button", { name: "Next" }).click();

    // Click "Edit" on Job Search section
    await page.getByRole("button", { name: /Edit/ }).first().click();

    // Should be back on Step 1
    await expect(page.getByText("Search Keywords")).toBeVisible();
    // Keywords should still be filled
    await expect(
      page.getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
    ).toHaveValue("React");
  });

  // -- Navigation --

  test("Back button navigates to previous step", async ({ page }) => {
    // Navigate to step 2
    await page
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("Your Resume", { exact: true })).toBeVisible();

    // Go back
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

    // Wait for debounced save (300ms + buffer)
    await page.waitForTimeout(500);

    // Refresh
    await page.reload();

    // Data should still be there
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
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React, Python");
    await page
      .getByPlaceholder("e.g. San Francisco, New York, Austin")
      .fill("San Francisco");
    await page.getByText("Remote only").click();
    await page.getByPlaceholder("e.g. 120000").fill("150000");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("Senior Software Engineer with 8 years of experience.");
    await page
      .getByPlaceholder("https://linkedin.com/in/yourprofile")
      .fill("https://linkedin.com/in/test");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: Submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

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
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("Resume text");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: Submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

    await expect(page.getByText(/Failed to start session/)).toBeVisible();
  });

  test("shows loading state while submitting", async ({ page }) => {
    await page.route("**/api/sessions", async (route) => {
      if (route.request().method() === "POST") {
        await new Promise((resolve) => setTimeout(resolve, 1000));
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
      .getByPlaceholder("e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner")
      .fill("React");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("Resume text");
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: Submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

    await expect(
      page.getByRole("button", { name: "Starting session..." })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Starting session..." })
    ).toBeDisabled();
  });
});
