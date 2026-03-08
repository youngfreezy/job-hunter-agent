// Copyright (c) 2026 V2 Software LLC. All rights reserved.

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
  await page.context().addCookies([
    {
      name: "jobhunter_test_bypass",
      value: "1",
      domain: "localhost",
      path: "/",
      httpOnly: false,
      sameSite: "Lax",
    },
  ]);
  await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
  await Promise.race([
    page
      .getByRole("button", { name: "Start New Session" })
      .waitFor({ state: "visible", timeout: 30_000 }),
    page
      .getByRole("heading", {
        name: "Keep sessions moving without losing context",
      })
      .waitFor({ state: "visible", timeout: 30_000 }),
  ]);
  await expect(page).toHaveURL(/\/dashboard/);
}
