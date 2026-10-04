import { test, expect } from "@playwright/test";

// These checks use real NextAuth middleware. Only the external OAuth handoff is
// stubbed; the live Google callback is also checked manually before release.
test.describe("Authentication entry points", () => {
  for (const route of ["/session/new", "/dashboard", "/settings", "/account", "/billing", "/quick-apply", "/developer", "/autopilot"]) {
    test(`protects ${route} and retains the return destination`, async ({ page }) => {
      await page.goto(route);
      await expect(page).toHaveURL(/\/auth\/login\?/);
      const callback = new URL(page.url()).searchParams.get("callbackUrl");
      expect(new URL(callback!, page.url()).pathname).toBe(route);
    });
  }

  test("offers Google signup, working policies and a preserved return path", async ({ page }) => {
    await page.goto("/auth/signup?callbackUrl=%2Fquick-apply");
    await expect(page.getByText("Create your account", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute("href", "/auth/login?callbackUrl=%2Fquick-apply");
    await expect(page.getByRole("link", { name: "Terms of Service", exact: true }).first()).toHaveAttribute("href", "/terms");
    await expect(page.getByRole("link", { name: "Privacy Policy", exact: true }).first()).toHaveAttribute("href", "/privacy");
    await expect(page.getByText("We use Gmail access", { exact: false })).toHaveCount(0);
  });

  test("retains a deep link through the OAuth POST", async ({ page }) => {
    await page.route("**/api/auth/providers", (route) => route.fulfill({ json: { google: { id: "google", name: "Google", type: "oauth", signinUrl: "/api/auth/signin/google", callbackUrl: "/api/auth/callback/google" } } }));
    await page.route("**/api/auth/csrf", (route) => route.fulfill({ json: { csrfToken: "test-csrf" } }));
    let callback = "";
    await page.route("**/api/auth/signin/google", async (route) => {
      callback = new URLSearchParams(route.request().postData() || "").get("callbackUrl") || "";
      await route.fulfill({ json: { url: new URL("/oauth-test-finish", page.url()).toString() } });
    });
    await page.route("**/oauth-test-finish", (route) => route.fulfill({ contentType: "text/html", body: "<h1>OAuth handoff captured</h1>" }));
    await page.goto("/auth/login?callbackUrl=%2Fsession%2Fnew%3Fmode%3Dquick");
    const button = page.getByRole("button", { name: "Continue with Google" });
    await expect(button).toBeEnabled();
    await button.click();
    await expect(page.getByRole("heading", { name: "OAuth handoff captured" })).toBeVisible();
    expect(callback).toBe("/session/new?mode=quick");
  });

  test("rejects an external callback while keeping a usable signup link", async ({ page }) => {
    await page.goto("/auth/login?callbackUrl=https%3A%2F%2Fevil.example%2F");
    await expect(page.getByRole("link", { name: "Sign up", exact: true })).toHaveAttribute("href", "/auth/signup?callbackUrl=%2Fdashboard");
  });

  test("shows recoverable OAuth errors", async ({ page }) => {
    await page.goto("/auth/login?error=OAuthCallback");
    await expect(page.getByRole("alert").filter({ hasText: "Sign-in could not be completed" })).toBeVisible();
  });

  test("token endpoint rejects a logged-out visitor without caching", async ({ request }) => {
    const response = await request.get("/api/auth/token");
    expect(response.status()).toBe(401);
    expect(response.headers()["cache-control"]).toContain("no-store");
  });
});
