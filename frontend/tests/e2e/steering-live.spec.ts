import { test, expect } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

test.describe("Live Steering Integration", () => {
  test("chat steering sends command to live backend and receives acknowledgement", async ({
    page,
  }) => {
    test.setTimeout(180_000);

    await login(page);

    // Create a real session via backend API (no route mocking).
    const createRes = await page.request.post(`${API_BASE}/api/sessions`, {
      data: {
        keywords: ["Python", "Backend Engineer"],
        locations: ["Remote"],
        remote_only: true,
        salary_min: 120000,
        resume_text:
          "Test User\nSenior Backend Engineer\ntest@example.com\n5 years Python, FastAPI, AWS, Docker, PostgreSQL",
        linkedin_url: null,
        preferences: {},
      },
    });
    expect(createRes.status()).toBe(200);
    const { session_id: sessionId } = await createRes.json();

    await page.goto(`/session/${sessionId}`);
    await expect(page.getByText("Session Steering")).toBeVisible({
      timeout: 20_000,
    });

    const command = "skip next job";
    await page.getByPlaceholder("Ask the agent to adjust...").fill(command);
    await page.getByRole("button", { name: "Send" }).click();

    const steeringPanel = page.locator("div").filter({
      has: page.getByText("Session Steering"),
    });

    // User message should render in chat immediately.
    await expect(steeringPanel.getByText(command)).toBeVisible({
      timeout: 10_000,
    });

    // Backend acknowledgement from /steer should stream back into the UI.
    await expect(steeringPanel.getByText(`Got it — adjusting based on your feedback: ${command}`).first()).toBeVisible({
      timeout: 20_000,
    });
  });
});
