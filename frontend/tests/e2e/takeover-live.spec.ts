import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers/auth";

const API_BASE = "http://localhost:8000";

type Rect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

async function waitForTakeoverState(
  page: Page,
  sessionId: string,
  predicate: (state: Record<string, unknown>) => boolean,
  timeoutMs = 20_000
): Promise<Record<string, unknown>> {
  const deadline = Date.now() + timeoutMs;
  let lastState: Record<string, unknown> = {};

  while (Date.now() < deadline) {
    const response = await page.request.get(
      `${API_BASE}/api/sessions/${sessionId}/takeover-state`
    );
    expect(response.ok()).toBeTruthy();
    lastState = (await response.json()) as Record<string, unknown>;
    if (predicate(lastState)) {
      return lastState;
    }
    await page.waitForTimeout(500);
  }

  throw new Error(
    `Timed out waiting for takeover state. Last state: ${JSON.stringify(lastState)}`
  );
}

async function clickRemotePoint(
  page: Page,
  remoteX: number,
  remoteY: number
): Promise<void> {
  const image = page.getByTestId("takeover-image");
  let box = await image.boundingBox();
  let dimensions = await image.evaluate((node) => ({
    naturalWidth: (node as HTMLImageElement).naturalWidth,
    naturalHeight: (node as HTMLImageElement).naturalHeight,
  }));

  for (let attempt = 0; attempt < 10; attempt++) {
    if (
      box &&
      dimensions.naturalWidth > 0 &&
      dimensions.naturalHeight > 0
    ) {
      break;
    }
    await page.waitForTimeout(300);
    box = await image.boundingBox();
    dimensions = await image.evaluate((node) => ({
      naturalWidth: (node as HTMLImageElement).naturalWidth,
      naturalHeight: (node as HTMLImageElement).naturalHeight,
    }));
  }

  expect(box).not.toBeNull();
  if (!box || !dimensions.naturalWidth || !dimensions.naturalHeight) {
    throw new Error("Takeover image was not fully loaded");
  }

  const containerRatio = box.width / box.height;
  const imageRatio = dimensions.naturalWidth / dimensions.naturalHeight;

  let renderedWidth = box.width;
  let renderedHeight = box.height;
  let offsetX = 0;
  let offsetY = 0;

  if (containerRatio > imageRatio) {
    renderedWidth = box.height * imageRatio;
    offsetX = (box.width - renderedWidth) / 2;
  } else {
    renderedHeight = box.width / imageRatio;
    offsetY = (box.height - renderedHeight) / 2;
  }

  await page.mouse.click(
    box.x + offsetX + (remoteX / dimensions.naturalWidth) * renderedWidth,
    box.y + offsetY + (remoteY / dimensions.naturalHeight) * renderedHeight
  );
}

test.describe("Live Browser Takeover", () => {
  test("UI can take control of the live Playwright page end-to-end", async ({
    page,
  }) => {
    test.setTimeout(180_000);

    await login(page);

    const createRes = await page.request.post(
      `${API_BASE}/api/sessions/test-takeover`,
      {
        data: {},
      }
    );
    expect(createRes.ok()).toBeTruthy();
    const { session_id: sessionId } = await createRes.json();

    await page.goto(`/session/${sessionId}`);
    await expect(page.getByText("Browser Takeover")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByTestId("takeover-image")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText("Live takeover page is ready.")).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole("button", { name: "Take Control" }).click();
    await expect(
      page.getByRole("button", { name: "Release Control" })
    ).toBeVisible({
      timeout: 10_000,
    });

    const readyState = await waitForTakeoverState(
      page,
      sessionId,
      (state) =>
        state.available === true &&
        typeof state.inputRect === "object" &&
        state.inputRect !== null &&
        typeof state.buttonRect === "object" &&
        state.buttonRect !== null
    );

    const inputRect = readyState.inputRect as Rect;
    const buttonRect = readyState.buttonRect as Rect;

    await clickRemotePoint(
      page,
      inputRect.left + inputRect.width / 2,
      inputRect.top + inputRect.height / 2
    );
    await page.getByTestId("takeover-container").focus();
    await page.keyboard.type("Jane takeover");

    const typedState = await waitForTakeoverState(
      page,
      sessionId,
      (state) =>
        state.inputValue === "Jane takeover" &&
        state.mirror === "Jane takeover"
    );
    expect(typedState.title).toBe("Takeover Smoke Test");

    await clickRemotePoint(
      page,
      buttonRect.left + buttonRect.width / 2,
      buttonRect.top + buttonRect.height / 2
    );

    const clickedState = await waitForTakeoverState(
      page,
      sessionId,
      (state) => state.clickCount === "1"
    );
    expect(clickedState.available).toBe(true);
  });
});
