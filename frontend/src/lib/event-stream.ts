/** EventSource-compatible subscription with credentials kept out of URLs. */
export class AuthenticatedEventSource extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  readyState = AuthenticatedEventSource.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  private controller = new AbortController();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private lastEventId = "";
  private retryMs = 3000;

  constructor(private url: string, private headers: () => Promise<Record<string, string>>) {
    super();
    // Give the caller time to attach listeners, as native EventSource does.
    this.timer = setTimeout(() => void this.connect(), 0);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void, options?: AddEventListenerOptions | boolean): void;
  addEventListener(type: string, listener: EventListenerOrEventListenerObject | null, options?: AddEventListenerOptions | boolean): void;
  addEventListener(type: string, listener: EventListenerOrEventListenerObject | ((event: MessageEvent) => void) | null, options?: AddEventListenerOptions | boolean): void {
    super.addEventListener(type, listener as EventListenerOrEventListenerObject | null, options);
  }

  close(): void {
    this.readyState = AuthenticatedEventSource.CLOSED;
    clearTimeout(this.timer);
    this.controller.abort();
  }

  private emit(event: Event): void {
    this.dispatchEvent(event);
    if (event.type === "open") this.onopen?.(event);
    else if (event.type === "error") this.onerror?.(event);
    else if (event.type === "message") this.onmessage?.(event as MessageEvent);
  }

  private async connect(): Promise<void> {
    if (this.controller.signal.aborted) return;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    let terminalFailure = false;
    try {
      const headers = await this.headers();
      if (this.controller.signal.aborted) return;
      const response = await fetch(this.url, {
        headers: { ...headers, Accept: "text/event-stream", ...(this.lastEventId ? { "Last-Event-ID": this.lastEventId } : {}) },
        cache: "no-store",
        redirect: "error",
        signal: this.controller.signal,
      });
      if (response.status === 204) { this.close(); return; }
      if (!response.ok || !response.headers.get("Content-Type")?.startsWith("text/event-stream") || !response.body) {
        // Authentication/authorization failures must not retry indefinitely.
        if (response.status >= 400 && response.status < 500 && response.status !== 429) {
          terminalFailure = true;
          this.close();
        }
        throw new Error("Event stream unavailable");
      }
      this.readyState = AuthenticatedEventSource.OPEN;
      this.emit(new Event("open"));
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let eventType = "";
      let data: string[] = [];
      let dataSize = 0;
      let skipLF = false;
      const line = (value: string) => {
        if (!value) {
          if (data.length) this.emit(new MessageEvent(eventType || "message", { data: data.join("\n"), lastEventId: this.lastEventId }));
          eventType = ""; data = []; dataSize = 0;
          return;
        }
        if (value.startsWith(":")) return;
        const colon = value.indexOf(":");
        const field = colon < 0 ? value : value.slice(0, colon);
        const content = colon < 0 ? "" : value.slice(colon + 1).replace(/^ /, "");
        if (field === "data") {
          dataSize += content.length + 1;
          if (dataSize > 1024 * 1024) throw new Error("Event stream event too large");
          data.push(content);
        }
        else if (field === "event") eventType = content;
        else if (field === "id" && !content.includes("\0")) this.lastEventId = content;
        else if (field === "retry" && /^\d+$/.test(content)) this.retryMs = Math.min(30000, Math.max(1000, Number(content)));
      };
      while (!this.controller.signal.aborted) {
        const chunk = await reader.read();
        if (chunk.done) break;
        for (const character of decoder.decode(chunk.value, { stream: true })) {
          if (skipLF) { skipLF = false; if (character === "\n") continue; }
          if (character === "\n" || character === "\r") {
            line(buffer); buffer = ""; skipLF = character === "\r";
            if (this.controller.signal.aborted) break;
          } else {
            buffer += character;
            if (buffer.length > 1024 * 1024) throw new Error("Event stream line too large");
          }
        }
      }
      if (!this.controller.signal.aborted) throw new Error("Event stream disconnected");
    } catch {
      if (this.controller.signal.aborted && !terminalFailure) return;
      if (this.readyState !== AuthenticatedEventSource.CLOSED) this.readyState = AuthenticatedEventSource.CONNECTING;
      this.emit(new Event("error"));
      if (!this.controller.signal.aborted) this.timer = setTimeout(() => void this.connect(), this.retryMs);
    } finally {
      await reader?.cancel().catch(() => {});
      reader?.releaseLock();
    }
  }
}
