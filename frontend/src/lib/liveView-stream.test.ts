import { afterEach, expect, it, vi } from "vitest";
import { connectSSE } from "./api";
import { liveViewEnds } from "./liveView";

afterEach(() => vi.unstubAllGlobals());

it("delivers browser closure events through the real SSE subscription", async () => {
  const close = vi.fn();
  const source = Object.assign(new EventTarget(), { close });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
  const addListener = vi.spyOn(source, "addEventListener");
  vi.stubGlobal("EventSource", vi.fn(function () { return source; }));
  const receive = vi.fn();
  const disconnect = connectSSE("test-session", receive);
  await vi.waitFor(() => expect(addListener).toHaveBeenCalled());
  source.dispatchEvent(new MessageEvent("browser_live_view_ended", {
    data: JSON.stringify({ browserbase_session_id: "closed-browser" }),
  }));
  expect(receive).toHaveBeenCalledOnce();
  expect(liveViewEnds(receive.mock.calls[0][0])).toBe(true);
  expect(close).not.toHaveBeenCalled(); // The pipeline continues after the browser closes.
  disconnect();
  expect(close).toHaveBeenCalledOnce();
});
