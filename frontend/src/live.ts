// Live-Verbindung: Snapshot per REST, Ereignisse per Server-Sent Events.
// Nach einem Verbindungsabbruch wird automatisch neu verbunden und der tatsächliche Zustand
// aus dem Backend nachgeladen (Snapshot + Ereignisse nach der letzten bekannten ID).
import type { Api } from "./api";
import type { Action } from "./store";
import type { EventItem, Snapshot } from "./types";

export interface EventSourceLike {
  onopen: ((ev: Event) => void) | null;
  onerror: ((ev: Event) => void) | null;
  addEventListener(type: string, cb: (ev: MessageEvent) => void): void;
  close(): void;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export interface LiveOptions {
  api: Pick<Api, "get" | "streamUrl">;
  dispatch: (a: Action) => void;
  makeEventSource?: EventSourceFactory;
  refreshDebounceMs?: number;
  pollMs?: number;
  setTimer?: typeof setTimeout;
  clearTimer?: typeof clearTimeout;
}

export class LiveConnection {
  private es: EventSourceLike | null = null;
  private lastId = 0;
  private retry = 0;
  private stopped = false;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private o: Required<LiveOptions>;
  private seq = 0;
  private applied = 0;

  constructor(opts: LiveOptions) {
    this.o = {
      makeEventSource: (url) => new EventSource(url) as unknown as EventSourceLike,
      // Wrapper nötig: setTimeout darf im Browser nicht mit fremdem `this` aufgerufen werden
      refreshDebounceMs: 400, pollMs: 10000,
      setTimer: ((fn: () => void, ms?: number) => setTimeout(fn, ms)) as typeof setTimeout,
      clearTimer: ((id?: ReturnType<typeof setTimeout>) => clearTimeout(id)) as typeof clearTimeout, ...opts,
    } as Required<LiveOptions>;
  }

  async start() {
    this.stopped = false;
    await this.sync(true);
    this.open();
    this.pollTimer = setInterval(() => void this.refresh(), this.o.pollMs);
  }

  stop() {
    this.stopped = true;
    this.es?.close();
    this.es = null;
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.refreshTimer) this.o.clearTimer(this.refreshTimer);
    if (this.retryTimer) this.o.clearTimer(this.retryTimer);
  }

  /** Vollständige Synchronisierung: Snapshot + fehlende Ereignisse. */
  async sync(initial = false): Promise<boolean> {
    try {
      const snap = await this.o.api.get<Snapshot>("/api/state");
      this.o.dispatch({ type: "snapshot", snapshot: snap, at: Date.now() });
      const path = initial || this.lastId === 0 ? "/api/events?latest=true&limit=300" : `/api/events?after_id=${this.lastId}&limit=2000`;
      const events = await this.o.api.get<EventItem[]>(path);
      this.ingest(events);
      if (initial && this.lastId === 0) this.lastId = snap.last_event_id;
      return true;
    } catch (err) {
      this.o.dispatch({ type: "conn", conn: "offline", error: String((err as Error).message || err) });
      return false;
    }
  }

  async refresh() {
    const mySeq = ++this.seq;
    try {
      const snap = await this.o.api.get<Snapshot>("/api/state");
      if (mySeq < this.applied) return; // ältere Antwort darf einen neueren Stand nicht überschreiben
      this.applied = mySeq;
      this.o.dispatch({ type: "snapshot", snapshot: snap, at: Date.now() });
    } catch (err) {
      this.o.dispatch({ type: "conn", conn: "offline", error: String((err as Error).message || err) });
    }
  }

  private ingest(events: EventItem[]) {
    if (!events.length) return;
    this.lastId = Math.max(this.lastId, ...events.map((e) => e.id));
    this.o.dispatch({ type: "events", events });
  }

  private scheduleRefresh() {
    if (this.refreshTimer) return;
    this.refreshTimer = this.o.setTimer(() => {
      this.refreshTimer = null;
      void this.refresh();
    }, this.o.refreshDebounceMs);
  }

  private open() {
    if (this.stopped) return;
    const es = this.o.makeEventSource(this.o.api.streamUrl(this.lastId));
    this.es = es;
    es.onopen = () => {
      this.retry = 0;
      this.o.dispatch({ type: "conn", conn: "live" });
    };
    es.addEventListener("ev", (msg: MessageEvent) => {
      let parsed: EventItem;
      try { parsed = JSON.parse(msg.data) as EventItem; } catch { return; /* defekte Nachricht ignorieren */ }
      this.ingest([parsed]);
      this.scheduleRefresh();
    });
    es.onerror = () => {
      // Eigene Wiederverbindung mit Backoff und anschließender Resynchronisierung
      es.close();
      if (this.es === es) this.es = null;
      if (this.stopped) return;
      this.o.dispatch({ type: "conn", conn: "reconnecting" });
      const delay = Math.min(10000, 1000 * 2 ** this.retry++);
      this.retryTimer = this.o.setTimer(async () => {
        const ok = await this.sync();
        if (!ok) this.o.dispatch({ type: "conn", conn: "offline" });
        this.open();
      }, delay);
    };
  }
}
