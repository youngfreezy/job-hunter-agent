import { afterEach, expect, it, vi } from "vitest";

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); });

it("streams named events using Authorization headers and never a token URL", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  const stream = new ReadableStream<Uint8Array>({ start(controller) {
    controller.enqueue(new TextEncoder().encode('event: browser_live_view_ended\r\ndata: {"browserbase_session_id":"closed-browser"}\r\n\r\n'));
  } });
  vi.stubGlobal("EventSource", vi.fn(function () { return Object.assign(new EventTarget(), { close: vi.fn() }); }));
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    requests.push({ url, init });
    return url === "/api/auth/token"
      ? Response.json({ token: "synthetic-audit-token" })
      : new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
  }));
  const { connectSSE } = await import("./api");
  const events = vi.fn();
  const stop = connectSSE("audit-session", events);
  try {
    await vi.waitFor(() => expect(events).toHaveBeenCalledOnce());
    expect(events.mock.calls[0][0].event).toBe("browser_live_view_ended");
    expect(requests[1].url).toMatch(/\/api\/sessions\/audit-session\/stream$/);
    expect(new Headers(requests[1].init?.headers).get("Authorization")).toBe("Bearer synthetic-audit-token");
    expect(requests.some(({ url }) => url.includes("synthetic-audit-token"))).toBe(false);
  } finally { stop(); }
});
