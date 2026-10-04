import { afterEach, expect, it, vi } from "vitest";
import { AuthenticatedEventSource } from "./event-stream";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

const encoded = (text: string) => new TextEncoder().encode(text);
const response = (chunks: Uint8Array[], close = false) => new Response(new ReadableStream({ start(c) {
  chunks.forEach(chunk => c.enqueue(chunk));
  if (close) c.close();
} }), { headers: { "Content-Type": "text/event-stream" } });

it("parses chunked CRLF, multiline data, comments and split UTF-8", async () => {
  const bytes = encoded(': keepalive\r\nid: 7\r\nevent: coaching\r\ndata: résumé\r\ndata: second line\r\n\r\n');
  vi.stubGlobal("fetch", vi.fn(async () => response(Array.from(bytes, byte => new Uint8Array([byte])))));
  const source = new AuthenticatedEventSource("/stream", async () => ({}));
  const events = vi.fn();
  source.addEventListener("coaching", events);
  try {
    await vi.waitFor(() => expect(events).toHaveBeenCalledOnce());
    expect(events.mock.calls[0][0].data).toBe("résumé\nsecond line");
    expect(events.mock.calls[0][0].lastEventId).toBe("7");
  } finally { source.close(); }
});

it("reconnects after EOF with a fresh authorization header and last event ID", async () => {
  vi.useFakeTimers();
  const headers = vi.fn().mockResolvedValueOnce({ Authorization: "Bearer first" }).mockResolvedValue({ Authorization: "Bearer refreshed" });
  const fetcher = vi.fn().mockResolvedValueOnce(response([encoded('id: 7\ndata: first\n\n')], true)).mockResolvedValue(response([]));
  vi.stubGlobal("fetch", fetcher);
  const source = new AuthenticatedEventSource("/stream", headers);
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(3000);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(fetcher.mock.calls[1][1].headers).toMatchObject({ Authorization: "Bearer refreshed", "Last-Event-ID": "7" });
  source.close();
});

it("stops on authorization errors without endless retries", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn(async () => new Response(null, { status: 403 }));
  vi.stubGlobal("fetch", fetcher);
  const source = new AuthenticatedEventSource("/stream", async () => ({}));
  const error = vi.fn(); source.onerror = error;
  await vi.advanceTimersByTimeAsync(10000);
  expect(fetcher).toHaveBeenCalledOnce();
  expect(error).toHaveBeenCalledOnce();
  expect(source.readyState).toBe(AuthenticatedEventSource.CLOSED);
});

it("cleanup during token lookup never opens a connection", async () => {
  let finish!: (value: Record<string, string>) => void;
  const headers = new Promise<Record<string, string>>(resolve => { finish = resolve; });
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  const source = new AuthenticatedEventSource("/stream", () => headers);
  const error = vi.fn(); source.onerror = error;
  await new Promise(resolve => setTimeout(resolve, 5));
  source.close(); finish({ Authorization: "Bearer fixture" });
  await Promise.resolve();
  expect(fetcher).not.toHaveBeenCalled();
  expect(error).not.toHaveBeenCalled();
});
