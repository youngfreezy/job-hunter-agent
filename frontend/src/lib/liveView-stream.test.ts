import { afterEach, expect, it, vi } from "vitest";
import { connectSSE } from "./api";
import { liveViewEnds } from "./liveView";

afterEach(() => vi.unstubAllGlobals());

it("delivers browser closure events without closing the pipeline subscription", async () => {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  const cancel = vi.fn();
  const stream = new ReadableStream<Uint8Array>({ start(c) { controller = c; }, cancel });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => url === "/api/auth/token"
    ? Response.json({ token: "test-token" })
    : new Response(stream, { headers: { "Content-Type": "text/event-stream" } })));
  const receive = vi.fn();
  const connected = vi.fn();
  const disconnect = connectSSE("test-session", receive, connected);
  await vi.waitFor(() => expect(connected).toHaveBeenCalledWith(true));
  controller!.enqueue(new TextEncoder().encode('event: browser_live_view_ended\ndata: {"browserbase_session_id":"closed-browser"}\n\n'));
  await vi.waitFor(() => expect(receive).toHaveBeenCalledOnce());
  expect(liveViewEnds(receive.mock.calls[0][0])).toBe(true);
  expect(cancel).not.toHaveBeenCalled();
  disconnect();
});
