import type { RecordingState } from '@elderly-care/shared';

export interface ServerResponsePayload {
  type: 'response';
  degraded?: boolean;
  response?: string;
  audioUrl?: string;
  retryAfterSeconds?: number;
  transcript?: string;
}

interface ServerStatePayload {
  type: 'state';
  state: RecordingState;
  conversationId?: string;
  traceId?: string;
}

type ServerPayload = ServerResponsePayload | ServerStatePayload;

const MAX_RECONNECT_ATTEMPTS = 5;

/**
 * WebSocketClient (design.md §前端層). Wire protocol matches the backend's
 * $connect/control/audio routes (packages/backend/src/workflow/handlers):
 *  - connect: no reusable credential may appear in the URL. The future speech
 *    gateway must issue and consume a short-lived, single-use connection ticket.
 *  - control route: { action: "control", type: "start" | "stop" | "cancel" }
 *  - audio route:   { action: "audio", audioBase64, encoding, sampleRate }
 * `action` is API Gateway's routeSelectionExpression key, not a payload
 * field — the control route's actual command lives in `type` to avoid
 * colliding with it.
 */
export class VoiceWebSocketClient {
  private ws: WebSocket | null = null;
  private wsUrl: string | null = null;
  private reconnectAttempts = 0;
  private pendingQueue: unknown[] = [];

  private stateChangeCallbacks: ((state: RecordingState) => void)[] = [];
  private transcriptCallbacks: ((text: string) => void)[] = [];
  private responseCallbacks: ((payload: ServerResponsePayload) => void)[] = [];

  connect(wsUrl: string): Promise<void> {
    this.wsUrl = wsUrl;
    return this.openSocket();
  }

  private openSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.wsUrl!);
      ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.flushQueue();
        resolve();
      };
      ws.onerror = () => reject(new Error('WEBSOCKET_CONNECT_FAILED'));
      ws.onmessage = (event) => this.handleMessage(event);
      ws.onclose = () => this.handleClose();
      this.ws = ws;
    });
  }

  private handleClose(): void {
    if (!this.wsUrl || this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) return;
    const delayMs = Math.min(1000 * 2 ** this.reconnectAttempts, 10_000);
    this.reconnectAttempts++;
    setTimeout(() => {
      this.openSocket().catch(() => {
        /* handleClose will schedule the next attempt */
      });
    }, delayMs);
  }

  private handleMessage(event: MessageEvent<string>): void {
    let data: ServerPayload;
    try {
      data = JSON.parse(event.data) as ServerPayload;
    } catch {
      return;
    }
    if (data.type === 'state') {
      this.stateChangeCallbacks.forEach((cb) => cb(data.state));
    } else if (data.type === 'response') {
      this.responseCallbacks.forEach((cb) => cb(data));
      if (data.transcript) this.transcriptCallbacks.forEach((cb) => cb(data.transcript!));
    }
  }

  private send(payload: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    } else {
      // Local buffering while disconnected — flushed on reconnect.
      this.pendingQueue.push(payload);
    }
  }

  private flushQueue(): void {
    const queued = this.pendingQueue.splice(0, this.pendingQueue.length);
    for (const payload of queued) this.send(payload);
  }

  startSession(): void {
    this.send({ action: 'control', type: 'start' });
  }

  stopSession(): void {
    this.send({ action: 'control', type: 'stop' });
  }

  cancelSession(): void {
    this.send({ action: 'control', type: 'cancel' });
  }

  sendAudio(audioBase64: string, encoding: 'pcm' | 'opus', sampleRate: number): void {
    this.send({ action: 'audio', audioBase64, encoding, sampleRate });
  }

  onStateChange(callback: (state: RecordingState) => void): void {
    this.stateChangeCallbacks.push(callback);
  }

  onTranscript(callback: (text: string) => void): void {
    this.transcriptCallbacks.push(callback);
  }

  onAudioResponse(callback: (payload: ServerResponsePayload) => void): void {
    this.responseCallbacks.push(callback);
  }

  disconnect(): void {
    this.wsUrl = null;
    this.ws?.close();
    this.ws = null;
  }
}
