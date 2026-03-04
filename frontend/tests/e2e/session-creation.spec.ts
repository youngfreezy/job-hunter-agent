import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

test.describe("Session Creation", () => {
  test.beforeEach(async ({ page }) => {
    // Log in before each test
    await login(page);
    // Navigate to the new session page
    await page.goto("/session/new");
    await expect(page).toHaveURL(/\/session\/new/);
  });

  test("session creation page shows all form sections", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "New Session" })
    ).toBeVisible();
    await expect(
      page.getByText(
        "Configure your job search. The AI will coach your resume, discover jobs, and apply for you."
      )
    ).toBeVisible();
  });

  test('shows "Search Keywords" card with input', async ({ page }) => {
    await expect(page.getByText("Search Keywords")).toBeVisible();
    await expect(
      page.getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
    ).toBeVisible();
    await expect(
      page.getByText(
        "Comma-separated. These are matched against job titles and descriptions."
      )
    ).toBeVisible();
  });

  test('shows "Location & Preferences" card with remote-only checkbox and salary input', async ({
    page,
  }) => {
    await expect(page.getByText("Location & Preferences")).toBeVisible();
    await expect(
      page.getByPlaceholder("e.g. San Francisco, New York, Austin")
    ).toBeVisible();
    await expect(page.getByText("Remote only")).toBeVisible();
    await expect(page.getByText("Min salary:")).toBeVisible();
    await expect(page.getByPlaceholder("e.g. 120000")).toBeVisible();
  });

  test('shows "Your Resume" card with textarea', async ({ page }) => {
    await expect(page.getByText("Your Resume", { exact: true })).toBeVisible();
    await expect(
      page.getByPlaceholder("Paste your full resume text here...")
    ).toBeVisible();
    await expect(
      page.getByText(
        "The AI Career Coach will analyze, score, and rewrite your resume before applying."
      )
    ).toBeVisible();
  });

  test('shows "LinkedIn Profile" card with URL input', async ({ page }) => {
    await expect(page.getByText("LinkedIn Profile")).toBeVisible();
    await expect(
      page.getByPlaceholder("https://linkedin.com/in/yourprofile")
    ).toBeVisible();
  });

  test("keywords input shows live Badge preview for comma-separated values", async ({
    page,
  }) => {
    const keywordsInput = page.getByPlaceholder(
      "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
    );

    // Type comma-separated keywords
    await keywordsInput.fill("React, Python, Machine Learning");

    // Verify badges appear for each keyword
    await expect(page.getByText("React").first()).toBeVisible();
    await expect(page.getByText("Python")).toBeVisible();
    await expect(page.getByText("Machine Learning")).toBeVisible();
  });

  test("form validation: submitting without keywords shows error", async ({
    page,
  }) => {
    // Fill resume but not keywords
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("My resume text here");

    // Click submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

    // Should show validation error
    await expect(
      page.getByText("Enter at least one keyword.")
    ).toBeVisible();
  });

  test("form validation: submitting without resume shows error", async ({
    page,
  }) => {
    // Fill keywords but not resume
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React, Python");

    // Click submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

    // Should show validation error
    await expect(page.getByText("Paste your resume text.")).toBeVisible();
  });

  test("can fill out all fields and submit successfully", async ({ page }) => {
    // Intercept the POST /api/sessions call and return a mock session_id
    const mockSessionId = "test-session-abc123";
    await page.route("**/api/sessions", async (route) => {
      if (route.request().method() === "POST") {
        // Verify the request body contains expected fields
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

    // Fill keywords
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React, Python, Senior Engineer");

    // Fill locations
    await page
      .getByPlaceholder("e.g. San Francisco, New York, Austin")
      .fill("San Francisco, Remote");

    // Toggle remote only
    await page.getByText("Remote only").click();

    // Fill salary
    await page.getByPlaceholder("e.g. 120000").fill("150000");

    // Fill resume
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill(
        "Senior Software Engineer with 8 years of experience in React, Python, and cloud technologies."
      );

    // Fill LinkedIn
    await page
      .getByPlaceholder("https://linkedin.com/in/yourprofile")
      .fill("https://linkedin.com/in/testuser");

    // Submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

    // Should redirect to the session page
    await page.waitForURL(`**/session/${mockSessionId}`, { timeout: 10_000 });
    expect(page.url()).toContain(`/session/${mockSessionId}`);
  });

  test("shows loading state while submitting", async ({ page }) => {
    // Set up a delayed response so we can observe loading state
    await page.route("**/api/sessions", async (route) => {
      if (route.request().method() === "POST") {
        // Add a delay to observe loading state
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

    // Fill required fields
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("Resume text");

    // Submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

    // Should show loading state
    await expect(
      page.getByRole("button", { name: "Starting session..." })
    ).toBeVisible();

    // Button should be disabled while loading
    await expect(
      page.getByRole("button", { name: "Starting session..." })
    ).toBeDisabled();
  });

  test("shows error message when session creation fails", async ({ page }) => {
    // Mock a failed API response
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

    // Fill required fields
    await page
      .getByPlaceholder(
        "e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner"
      )
      .fill("React");
    await page
      .getByPlaceholder("Paste your full resume text here...")
      .fill("Resume text");

    // Submit
    await page
      .getByRole("button", { name: "Start Job Hunt Session" })
      .click();

    // Should show error message
    await expect(page.getByText(/Failed to start session/)).toBeVisible();
  });
});
