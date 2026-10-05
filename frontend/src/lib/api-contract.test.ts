import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { rateLimitToast } = vi.hoisted(() => ({ rateLimitToast: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: rateLimitToast } }));

beforeEach(() => { vi.resetModules(); rateLimitToast.mockReset(); });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

function mockApi(body: unknown = {}, status = 200) {
  const request = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => {
    return url === "/api/auth/token"
      ? Response.json({ token: "contract-token" })
      : Response.json(body, { status, headers: status === 429 ? { "Retry-After": "7" } : {} });
  });
  vi.stubGlobal("fetch", request);
  vi.stubGlobal("document", { cookie: "csrf_token=csrf%20fixture" });
  return request;
}

describe("public API client contracts", () => {
  it("shares one cached token across feature clients and reads CSRF on every request", async () => {
    const request = mockApi({ application_rules: "Verified facts" });
    const api = await import("./api");
    await api.getApplicationRules();
    vi.stubGlobal("document", { cookie: "csrf_token=updated" });
    await api.getWallet();
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      "/api/auth/token", "/api/auth/me/application-rules", "/api/billing/wallet",
    ]);
    expect(request.mock.calls[1][1]?.headers).toEqual({ Authorization: "Bearer contract-token", "x-csrf-token": "csrf fixture" });
    expect(request.mock.calls[2][1]?.headers).toEqual({ Authorization: "Bearer contract-token", "x-csrf-token": "updated" });
  });

  it("refreshes an expired token and allows cookie auth when token lookup is unavailable", async () => {
    vi.useFakeTimers();
    const request = mockApi();
    const api = await import("./api");
    await api.getWallet();
    await vi.advanceTimersByTimeAsync(300001);
    request.mockImplementation(async (url) => url === "/api/auth/token"
      ? new Response(null, { status: 401 }) : Response.json({}));
    await api.getBrowserbaseSettings();
    expect(request.mock.calls.filter(([url]) => url === "/api/auth/token")).toHaveLength(2);
    expect(request.mock.calls.at(-1)?.[1]?.headers).toEqual({ "x-csrf-token": "csrf fixture" });
  });

  it("keeps public marketplace reads unauthenticated and URL-encodes filters", async () => {
    const request = mockApi({ agents: [] });
    const api = await import("./api");
    expect(await api.listMarketplaceAgents("resume & coaching")).toEqual([]);
    expect(request).toHaveBeenCalledExactlyOnceWith("/api/marketplace/agents?category=resume%20%26%20coaching", undefined);
  });

  it("preserves mutation methods, payloads, and configured error details without retrying", async () => {
    const request = mockApi({ detail: "Add your own Browserbase key" }, 403);
    const api = await import("./api");
    await expect(api.saveBrowserbaseSettings({ project_id: "project", proxies: true, context_ids: {} }))
      .rejects.toThrow("Add your own Browserbase key");
    expect(request.mock.calls.at(-1)).toEqual(["/api/browserbase/settings", {
      method: "PUT", headers: { "Content-Type": "application/json", Authorization: "Bearer contract-token", "x-csrf-token": "csrf fixture" },
      body: JSON.stringify({ project_id: "project", proxies: true, context_ids: {} }),
    }]);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("returns structured session errors and never retries a start POST", async () => {
    const request = mockApi({ detail: [{ msg: "budget is reserved" }] }, 503);
    const api = await import("./api");
    await expect(api.rerunSession("session-1")).rejects.toThrow('[{"msg":"budget is reserved"}]');
    expect(request.mock.calls.at(-1)?.[1]).toMatchObject({ method: "POST", body: "{}" });
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("keeps multipart resume identity and lets the browser set its boundary", async () => {
    const request = mockApi({ text: "Resume", filename: "resume.pdf", resume_uuid: "uuid", file_path: "/uploads/canonical.pdf" });
    const api = await import("./api");
    const file = new File(["resume"], "resume.pdf", { type: "application/pdf" });
    expect(await api.parseResume(file)).toMatchObject({ resume_uuid: "uuid", file_path: "/uploads/canonical.pdf" });
    const init = request.mock.calls.at(-1)?.[1];
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
    expect((init?.body as FormData).get("file")).toBe(file);
  });

  it("normalizes older sessions with null keywords and locations", async () => {
    mockApi([{ id: "old-session", keywords: null, locations: null }]);
    const api = await import("./api");
    expect(await api.listSessions(true)).toEqual([{ id: "old-session", keywords: [], locations: [] }]);
  });

  it("surfaces one rate-limit notice across features while returning the original failure", async () => {
    const request = mockApi({}, 429);
    const api = await import("./api");
    await expect(api.getWallet()).rejects.toThrow("Failed to fetch wallet");
    await expect(api.listAutopilotSchedules()).rejects.toThrow("Failed to list autopilot schedules");
    expect(rateLimitToast).toHaveBeenCalledExactlyOnceWith("Too many requests — please wait 7s and try again.");
    expect(request).toHaveBeenCalledTimes(3);
  });

  it("saves a trial token only after the public start succeeds", async () => {
    const storage = new Map<string, string>();
    vi.stubGlobal("localStorage", { setItem: (k: string, v: string) => storage.set(k, v), getItem: (k: string) => storage.get(k) ?? null });
    vi.stubGlobal("window", { location: { port: "" } });
    const request = mockApi({ session_id: "trial", trial_token: "trial-token", email: "fixture@example.test", name: null });
    const api = await import("./api");
    const params = { keywords: ["AI"], locations: ["SF"], remote_only: false, salary_min: null, resume_text: "Resume", resume_file_path: null, resume_uuid: null, linkedin_url: null, preferences: {} };
    await api.startFreeTrialSession(params);
    expect(api.getTrialToken()).toBe("trial-token");
    expect(api.getTrialEmail()).toBe("fixture@example.test");
    expect(request).toHaveBeenCalledExactlyOnceWith("/api/free-trial/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) });
  });

  it.each(["authenticated", "trial"])("routes named %s events, skips malformed data, closes on done, and ignores late events", async (mode) => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({ start(c) { controller = c; } });
    vi.stubGlobal("window", { location: { port: "" } });
    vi.stubGlobal("localStorage", { getItem: () => "trial-fixture" });
    const request = vi.fn(async (url: string) => url === "/api/auth/token" ? Response.json({ token: "auth-fixture" }) : new Response(stream, { headers: { "Content-Type": "text/event-stream" } }));
    vi.stubGlobal("fetch", request);
    const api = await import("./api");
    const event = vi.fn();
    const stop = (mode === "trial" ? api.connectTrialSSE : api.connectSSE)("session", event);
    try {
      controller.enqueue(new TextEncoder().encode('event: status\ndata: not-json\n\nevent: browser_live_view\ndata: {"session":"browser"}\n\nevent: done\ndata: {"timestamp":"finished"}\n\n'));
      await vi.waitFor(() => expect(event).toHaveBeenCalledTimes(2));
      expect(event.mock.calls[0][0]).toMatchObject({ event: "browser_live_view", session: "browser" });
      expect(event.mock.calls[1][0]).toEqual({ event: "done", timestamp: "finished" });
      stop();
      expect(request.mock.calls.filter(([url]) => url.includes("/stream"))).toHaveLength(1);
    } finally { stop(); }
  });
});
