import { test, expect } from "@playwright/test";

test.describe("Landing Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("loads the homepage successfully", async ({ page }) => {
    await expect(page).toHaveURL("/");
    await expect(page.locator("body")).toBeVisible();
  });

  test('shows "JobHunter Agent" title in the nav', async ({ page }) => {
    await expect(page.getByText("JobHunter Agent").first()).toBeVisible();
  });

  test("shows all three pricing cards with correct prices", async ({
    page,
  }) => {
    // Scroll to pricing section
    await page.locator("#pricing").scrollIntoViewIfNeeded();

    // Pricing cards are rendered inside the #pricing section
    const pricing = page.locator("#pricing");

    // Starter - $49/week
    await expect(pricing.getByText("Starter")).toBeVisible();
    await expect(pricing.getByText("$49")).toBeVisible();

    // Professional - $99/week
    await expect(pricing.getByText("Professional")).toBeVisible();
    await expect(pricing.getByText("$99")).toBeVisible();

    // Executive - $199/week
    await expect(pricing.getByText("Executive")).toBeVisible();
    await expect(pricing.getByText("$199")).toBeVisible();
  });

  test("shows the Professional plan as Most Popular", async ({ page }) => {
    await page.locator("#pricing").scrollIntoViewIfNeeded();
    await expect(page.getByText("Most Popular")).toBeVisible();
  });

  test('"Start Free Trial" buttons link to /session/new', async ({ page }) => {
    await page.locator("#pricing").scrollIntoViewIfNeeded();

    // All "Start Free Trial" buttons within pricing cards should link to /session/new
    const trialButtons = page.locator("#pricing a[href='/session/new']");
    const count = await trialButtons.count();
    expect(count).toBe(3);
  });

  test('shows "How It Works" section with 6 steps', async ({ page }) => {
    await expect(page.getByText("How It Works")).toBeVisible();

    // Verify all 6 step titles are present
    const stepTitles = [
      "Upload & Configure",
      "AI Career Coach",
      "Discover & Score",
      "Review & Approve",
      "Watch & Steer",
      "Get Results",
    ];

    for (const title of stepTitles) {
      await expect(page.getByText(title)).toBeVisible();
    }
  });

  test("shows V2 Software LLC in the footer", async ({ page }) => {
    await expect(page.getByText("V2 Software LLC")).toBeVisible();
  });

  test("has navigation links to Dashboard and Get Started", async ({
    page,
  }) => {
    await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Get Started" })
    ).toBeVisible();
  });

  test("hero section has correct headline text", async ({ page }) => {
    await expect(page.getByText("Stop applying to jobs.")).toBeVisible();
    await expect(page.getByText("Let AI do it for you.")).toBeVisible();
  });

  test('hero has "Start Your First Session" button linking to /session/new', async ({
    page,
  }) => {
    const sessionLink = page.getByRole("link", {
      name: "Start Your First Session",
    });
    await expect(sessionLink).toBeVisible();
    await expect(sessionLink).toHaveAttribute("href", "/session/new");
  });
});
