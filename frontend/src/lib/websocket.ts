/**
 * WebSocket manager for screenshot feed and chat steering.
 * Handles reconnection, message parsing, and frame throttling.
 */

type MessageHandler = (data: Record<string, unknown>) => void;
type StatusHandler = (
  status: "connecting" | "connected" | "disconnected" | "error"
) => void;

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string;
  private onMessage: MessageHandler;
  private onStatus: StatusHandler;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private maxReconnects = 10;
  private shouldReconnect = true;

  constructor(url: string, onMessage: MessageHandler, onStatus: StatusHandler) {
    this.url = url;
    this.onMessage = onMessage;
    this.onStatus = onStatus;
  }

  connect(): void {
    this.shouldReconnect = true;
    this.onStatus("connecting");

    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.onStatus("error");
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.onStatus("connected");
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.onMessage(data);
      } catch {
        // Binary frame (screenshot as raw bytes)
        if (event.data instanceof Blob) {
          const reader = new FileReader();
          reader.onload = () => {
            this.onMessage({
              type: "screenshot",
              image: reader.result as string,
              raw: true,
            });
          };
          reader.readAsDataURL(event.data);
        }
      }
    };

    this.ws.onerror = () => {
      this.onStatus("error");
    };

    this.ws.onclose = () => {
      this.onStatus("disconnected");
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnects) return;
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  sendChat(message: string): void {
    this.send({ type: "chat", message });
  }

  requestControl(): void {
    this.send({ type: "takeover", action: "request" });
  }

  releaseControl(): void {
    this.send({ type: "takeover", action: "release" });
  }

  sendTakeoverInput(data: Record<string, unknown>): void {
    this.send({ type: "takeover_input", ...data });
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
