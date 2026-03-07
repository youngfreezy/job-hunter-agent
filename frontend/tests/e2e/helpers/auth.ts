import { type Page, expect } from "@playwright/test";

/**
 * Shared authentication helper for E2E tests.
 *
 * Signs in via the credentials provider (dev mode accepts any email/password).
 * After login, waits for navigation to the dashboard.
 */
export async function login(
  page: Page,
  email = "test@example.com",
  password = "testpass123"
): Promise<void> {
  for (let attempt = 1; attempt <= 2; attempt++) {
    await page.goto("/auth/login");
    await expect(page.getByPlaceholder("Email")).toBeVisible({
      timeout: 30_000,
    });

    // Fill in the email/password form
    await page.getByPlaceholder("Email").fill(email);
    await page.getByPlaceholder("Password").fill(password);

    // Click the Sign In button
    await page.getByRole("button", { name: "Sign In" }).click();

    try {
      // The login handler redirects to /dashboard on success.
      await page.waitForURL("**/dashboard", { timeout: 30_000 });
      await expect(page.getByRole("button", { name: "Start New Session" })).toBeVisible();
      return;
    } catch {
      const url = page.url();
      // Occasionally in dev mode, the form submits before hydration and
      // lands back on /auth/login with query params. Retry once.
      if (attempt < 2 && url.includes("/auth/login?")) {
        continue;
      }
      throw new Error(`Login failed, current URL: ${url}`);
    }
  }
}
