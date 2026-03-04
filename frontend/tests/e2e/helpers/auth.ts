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
  await page.goto("/auth/login");

  // Fill in the email/password form
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Password").fill(password);

  // Click the Sign In button
  await page.getByRole("button", { name: "Sign In" }).click();

  // Wait for navigation away from the login page.
  // The login handler redirects to /dashboard on success.
  await page.waitForURL("**/dashboard", { timeout: 15_000 });

  // Verify we actually landed on the dashboard
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}
