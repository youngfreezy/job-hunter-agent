import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

test.describe("Authentication Flow", () => {
  test.describe("Protected routes redirect unauthenticated users", () => {
    test("visiting /session/new redirects to /auth/login", async ({ page }) => {
      await page.goto("/session/new");
      await page.waitForURL("**/auth/login**");
      expect(page.url()).toContain("/auth/login");
    });

    test("visiting /dashboard redirects to /auth/login", async ({ page }) => {
      await page.goto("/dashboard");
      await page.waitForURL("**/auth/login**");
      expect(page.url()).toContain("/auth/login");
    });
  });

  test.describe("Login page", () => {
    test.beforeEach(async ({ page }) => {
      await page.goto("/auth/login");
    });

    test("renders the login form with email and password fields", async ({
      page,
    }) => {
      await expect(page.getByText("Sign in to your account")).toBeVisible();
      await expect(page.getByPlaceholder("Email")).toBeVisible();
      await expect(page.getByPlaceholder("Password")).toBeVisible();
      await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
    });

    test("has a link to the signup page", async ({ page }) => {
      const signupLink = page.getByRole("link", { name: "Sign up" });
      await expect(signupLink).toBeVisible();
      await expect(signupLink).toHaveAttribute("href", "/auth/signup");
    });

    test("shows the Google OAuth button", async ({ page }) => {
      await expect(
        page.getByRole("button", { name: /Continue with Google/i })
      ).toBeVisible();
    });

    test('shows "JobHunter Agent" branding', async ({ page }) => {
      await expect(page.getByText("JobHunter Agent")).toBeVisible();
    });
  });

  test.describe("Signup page", () => {
    test.beforeEach(async ({ page }) => {
      await page.goto("/auth/signup");
    });

    test("renders the signup form with name, email, and password fields", async ({
      page,
    }) => {
      await expect(page.getByText("Create your account")).toBeVisible();
      await expect(page.getByPlaceholder("Full name")).toBeVisible();
      await expect(page.getByPlaceholder("Email")).toBeVisible();
      await expect(
        page.getByPlaceholder("Password (min 8 characters)")
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Create Account" })
      ).toBeVisible();
    });

    test("has a link to the login page", async ({ page }) => {
      const loginLink = page.getByRole("link", { name: "Sign in" });
      await expect(loginLink).toBeVisible();
      await expect(loginLink).toHaveAttribute("href", "/auth/login");
    });

    test("shows terms of service notice", async ({ page }) => {
      await expect(
        page.getByText("By signing up, you agree to our Terms of Service")
      ).toBeVisible();
    });
  });

  test.describe("Login functionality", () => {
    test("can log in with credentials (dev mode)", async ({ page }) => {
      await login(page);

      // After login, we should be on the dashboard
      await expect(page).toHaveURL(/\/dashboard/);
      await expect(
        page.getByRole("heading", { name: "Dashboard" })
      ).toBeVisible();
    });

    test("after login, can access /dashboard", async ({ page }) => {
      await login(page);

      await page.goto("/dashboard");
      await expect(page).toHaveURL(/\/dashboard/);
      await expect(
        page.getByRole("heading", { name: "Dashboard" })
      ).toBeVisible();
    });

    test("after login, can access /session/new", async ({ page }) => {
      await login(page);

      await page.goto("/session/new");
      await expect(page).toHaveURL(/\/session\/new/);
      await expect(
        page.getByRole("heading", { name: "New Session" })
      ).toBeVisible();
    });
  });
});
