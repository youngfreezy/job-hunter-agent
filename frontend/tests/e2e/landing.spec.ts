import { test, expect } from "@playwright/test";

test.describe("Landing Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
  });

  test("loads the homepage successfully", async ({ page }) => {
    await expect(page).toHaveURL("/");
    await expect(page.locator("body")).toBeVisible();
  });

  test('shows "JobHunter Agent" title in the nav', async ({ page }) => {
    await expect(page.getByText("JobHunter Agent").first()).toBeVisible();
  });

  test("shows all three pricing cards with monthly pricing by default", async ({
    page,
  }) => {
    // Scroll to pricing section
    await page.locator("#pricing").scrollIntoViewIfNeeded();

    // Pricing cards are rendered inside the #pricing section
    const pricing = page.locator("#pricing");

    await expect(pricing.getByText("Free", { exact: true })).toBeVisible();
    await expect(pricing.getByText("$0").first()).toBeVisible();

    await expect(pricing.getByText("Pro", { exact: true })).toBeVisible();
    await expect(pricing.getByText("$49").first()).toBeVisible();

    await expect(pricing.getByText("Power", { exact: true })).toBeVisible();
    await expect(pricing.getByText("$99").first()).toBeVisible();
    await expect(pricing.getByRole("button", { name: "Monthly" })).toBeVisible();
  });

  test("shows the Pro plan as Most Popular", async ({ page }) => {
    await page.locator("#pricing").scrollIntoViewIfNeeded();
    await expect(page.getByText("Most Popular")).toBeVisible();
  });

  test("pricing CTAs link to /session/new", async ({ page }) => {
    await page.locator("#pricing").scrollIntoViewIfNeeded();

    const trialButtons = page.locator("#pricing a[href='/session/new']");
    const count = await trialButtons.count();
    expect(count).toBe(3);
  });

  test('shows "How It Works" section with 6 steps', async ({ page }) => {
    await expect(page.getByText("How It Works")).toBeVisible();

    // Verify all 6 step titles are present
    const stepTitles = [
      "Tell it what you want",
      "Review the resume rewrite",
      "Pick from a ranked shortlist",
      "Stay in control while it applies",
      "See what happened for every job",
      "Pick back up without starting over",
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
    await expect(page.getByRole("link", { name: "Get Started" })).toBeVisible();
  });

  test("hero section has correct headline text", async ({ page }) => {
    await expect(
      page.getByText("Job searching should feel less chaotic.")
    ).toBeVisible();
    await expect(
      page.getByText("Keep your standards while the work gets done.")
    ).toBeVisible();
  });

  test('hero has "Start Free" button linking to /session/new', async ({
    page,
  }) => {
    const sessionLink = page.getByRole("link", { name: "Start Free" }).first();
    await expect(sessionLink).toBeVisible();
    await expect(sessionLink).toHaveAttribute("href", "/session/new");
  });
});
