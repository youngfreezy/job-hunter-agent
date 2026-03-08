// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { test, expect } from "@playwright/test";

test.describe("Backend Health Check", () => {
  test("GET /api/health returns 200 with status ok", async ({ request }) => {
    const response = await request.get("http://localhost:8000/api/health");

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.status).toBe("ok");
  });

  test("health endpoint includes version field", async ({ request }) => {
    const response = await request.get("http://localhost:8000/api/health");

    expect(response.ok()).toBeTruthy();

    const body = await response.json();
    expect(body).toHaveProperty("version");
  });
});
