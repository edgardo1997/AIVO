const WS_BASE = "ws://127.0.0.1:8765";

export interface LiveEvent {
  event_id: string;
  event_type: string;
  timestamp: number;
  session_id: string;
  request_id: string;
  parent_event_id: string | null;
  component: string;
  status: string;
  priority: string;
  progress: number | null;
  tool: string | null;
  message: string | null;
  details: Record<string, unknown> | null;
  duration: number | null;
}

export class EventStreamClient {
  private ws: WebSocket | null = null;
  private sessionId = "";
  private handlers = new Map<string, Set<(event: LiveEvent) => void>>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyHandlers = new Set<() => void>();

  connect(sessionId = ""): void {
    this.disconnect();
    this.sessionId = sessionId;
    this.reconnectAttempts = 0;
    this._connect();
  }

  private _connect(): void {
    const url = `${WS_BASE}/ws/events${this.sessionId ? `?session_id=${encodeURIComponent(this.sessionId)}` : ""}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (msg: MessageEvent) => {
      try {
        const event: LiveEvent = JSON.parse(msg.data);
        const eventHandlers = this.handlers.get(event.event_type);
        if (eventHandlers) {
          eventHandlers.forEach((handler) => handler(event));
        }
        const wildcardHandlers = this.handlers.get("*");
        if (wildcardHandlers) {
          wildcardHandlers.forEach((handler) => handler(event));
        }
      } catch {
        // ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private _scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    this.reconnectTimer = setTimeout(() => {
      this._connect();
    }, delay);
  }

  subscribe(eventType: string, handler: (event: LiveEvent) => void): void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, new Set());
    }
    this.handlers.get(eventType)!.add(handler);
  }

  unsubscribe(eventType: string, handler: (event: LiveEvent) => void): void {
    const handlers = this.handlers.get(eventType);
    if (handlers) {
      handlers.delete(handler);
      if (handlers.size === 0) {
        this.handlers.delete(eventType);
      }
    }
  }

  onDestroy(fn: () => void): void {
    this.destroyHandlers.add(fn);
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = this.maxReconnectAttempts;
    this.ws?.close();
    this.ws = null;
    this.destroyHandlers.forEach((fn) => fn());
    this.destroyHandlers.clear();
  }
}
