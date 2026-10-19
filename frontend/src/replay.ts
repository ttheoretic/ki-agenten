// Abspielmodus für die Online-Vorschau: spielt eine Aufzeichnung (scripts/record_preview.py) im
// unveränderten Control-Center ab. Alle Zustände und Ereignisse stammen aus einem echten Dry-Run;
// Steuerung und Freigaben sind in der Vorschau deaktiviert.
import { ApiError } from "./api";
import type { EventSourceLike } from "./live";
import type { AgentDetail, EventItem, Snapshot, TaskBrief } from "./types";

type TimedEvent = EventItem & { t: number };
interface StaticAgent { mission: string; responsibilities: string[]; rules: string[]; tools: string[]; write_dirs: string[];
  task_kinds: string[]; limits: { max_output_tokens: number; max_input_tokens: number } }
interface FullTask extends TaskBrief { goal: string; description: string; acceptance: string[]; result: unknown;
  history: { ts: string; status: string; note: string; from?: string }[]; feedback: { ts: string; from: string; message: string }[] }

export interface ReplayData {
  meta: { recorded_at: string; start_ms: number; duration: number; note: string };
  frames: { t: number; patch: Partial<Snapshot> }[];
  events: TimedEvent[];
  agents: Record<string, StaticAgent>;
  tasks: Record<string, FullTask>;
  files: { path: string; agent: string; kind: string; size: number; created_at: string; content: string }[];
}

export interface ApiLike {
  get<T>(path: string): Promise<T>;
  post<T>(path: string, body?: unknown): Promise<T>;
  streamUrl(afterId: number): string;
}

export class ReplayEngine {
  t: number;
  speed = 2;
  playing = true;
  private timer: ReturnType<typeof setInterval> | null = null;
  private sources = new Set<ReplaySource>();
  private listeners = new Set<() => void>();

  constructor(public data: ReplayData, startT = 0) {
    this.t = startT;
  }

  get duration() { return this.data.meta.duration; }
  /** Virtuelle Uhr: Zeitpunkt in der Aufzeichnung (für relative Zeiten und Kanten-Animation). */
  now() { return this.data.meta.start_ms + this.t * 1000; }

  start() {
    if (this.timer) return;
    this.timer = setInterval(() => {
      if (this.playing) {
        this.t = Math.min(this.duration, this.t + 0.1 * this.speed);
        if (this.t >= this.duration) this.playing = false;
      }
      for (const s of this.sources) s.pump();
      this.listeners.forEach((l) => l());
    }, 100);
  }

  stop() { if (this.timer) clearInterval(this.timer); this.timer = null; }
  subscribe(l: () => void) { this.listeners.add(l); return () => { this.listeners.delete(l); }; }
  seekForward(t: number) { this.t = Math.min(this.duration, Math.max(this.t, t)); }

  snapshot(): Snapshot {
    const snap: Record<string, unknown> = {};
    for (const f of this.data.frames) {
      if (f.t > this.t && Object.keys(snap).length) break;
      Object.assign(snap, f.patch);
    }
    return structuredClone(snap) as unknown as Snapshot;
  }

  eventsUntilNow(): TimedEvent[] { return this.data.events.filter((e) => e.t <= this.t); }

  attach(s: ReplaySource) { this.sources.add(s); }
  detach(s: ReplaySource) { this.sources.delete(s); }
}

export class ReplaySource implements EventSourceLike {
  onopen: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  private cb: ((ev: MessageEvent) => void)[] = [];
  private opened = false;

  constructor(private engine: ReplayEngine, private lastId: number) { engine.attach(this); }
  addEventListener(type: string, cb: (ev: MessageEvent) => void) { if (type === "ev") this.cb.push(cb); }
  close() { this.engine.detach(this); }

  pump() {
    if (!this.opened) { this.opened = true; this.onopen?.(new Event("open")); }
    for (const e of this.engine.data.events) {
      if (e.id <= this.lastId || e.t > this.engine.t) continue;
      this.lastId = e.id;
      const msg = { data: JSON.stringify(e) } as MessageEvent;
      this.cb.forEach((f) => f(msg));
    }
  }
}

const DISABLED = "In der Vorschau deaktiviert – Freigaben, Steuerung und Eingaben funktionieren in der lokalen Installation.";

export class ReplayApi implements ApiLike {
  token = "vorschau";
  constructor(private engine: ReplayEngine) {}

  streamUrl(afterId: number) { return `replay://${afterId}`; }
  makeEventSource = (url: string) => new ReplaySource(this.engine, Number(url.replace("replay://", "")) || 0);

  async post<T>(): Promise<T> { throw new ApiError(403, DISABLED); }

  async get<T>(path: string): Promise<T> {
    const url = new URL(path, "http://replay");
    const p = url.pathname, q = url.searchParams;
    const e = this.engine;
    const now = e.now();
    const snap = e.snapshot();
    const past = (ts: string | null | undefined) => !!ts && Date.parse(ts) <= now;
    const brief = (id: string | null) => (id ? snap.tasks.find((t) => t.id === id) ?? null : null);
    const events = e.eventsUntilNow();
    let m: RegExpMatchArray | null;

    if (p === "/api/state") return snap as T;
    if (p === "/api/events") {
      if (q.get("latest")) return events.slice(-Number(q.get("limit") || 300)) as T;
      const after = Number(q.get("after_id") || 0);
      return events.filter((x) => x.id > after) as T;
    }
    if ((m = p.match(/^\/api\/events\/(\d+)$/))) {
      const ev = events.find((x) => x.id === Number(m![1]));
      if (!ev) throw new ApiError(404, "Ereignis nicht gefunden");
      return { event: ev, task: brief(ev.task_id), approval: snap.approvals.find((a) => a.id === ev.approval_id) ?? null } as T;
    }
    if (p === "/api/communications") {
      const a = q.get("a"), b = q.get("b");
      return events.filter((x) => x.type.startsWith("comm.") && ((x.from_agent === a && x.to_agent === b) || (x.from_agent === b && x.to_agent === a)))
        .reverse().slice(0, 50).map((x) => ({ event: x, task: brief(x.task_id) })) as T;
    }
    if ((m = p.match(/^\/api\/agents\/(\w+)$/))) {
      const id = m[1];
      const ov = snap.agents.find((a) => a.id === id);
      if (!ov) throw new ApiError(404, "Unbekannter Agent");
      const mine = snap.tasks.filter((t) => t.agent === id);
      const comm = events.filter((x) => x.type.startsWith("comm.") && (x.from_agent === id || x.to_agent === id)).slice(-30).reverse();
      const warn = events.filter((x) => (x.agent === id || x.from_agent === id) && ["warning", "error", "critical"].includes(x.severity)).slice(-20).reverse();
      const full = (t: TaskBrief) => {
        const f = e.data.tasks[t.id];
        return { ...t, history: (f?.history ?? []).filter((h) => past(h.ts)), feedback: (f?.feedback ?? []).filter((x) => past(x.ts)) };
      };
      const detail: AgentDetail = {
        ...ov, ...e.data.agents[id],
        queue: mine.filter((t) => t.status === "pending" || t.status === "review"),
        completed_tasks: mine.filter((t) => t.status === "completed"),
        failed_tasks: mine.filter((t) => t.status === "failed" || t.status === "blocked"),
        history: mine.map(full),
        results: mine.filter((t) => t.status === "completed").map((t) => ({ task_id: t.id, title: t.title, artifacts: t.artifacts, completed_at: t.completed_at })),
        communications: comm, warnings: warn,
        next_step: ov.next_task ? { type: "planned", task: ov.next_task } : null,
        running_action: ov.current_task ? { type: "running", task: ov.current_task } : null,
      };
      return detail as T;
    }
    if ((m = p.match(/^\/api\/tasks\/([\w-]+)$/))) {
      const b = brief(m[1]);
      const f = e.data.tasks[m[1]];
      if (!b || !f) throw new ApiError(404, "Aufgabe existiert zu diesem Zeitpunkt noch nicht");
      const done = b.status === "completed" || b.status === "review";
      return { ...f, ...b, result: done ? f.result : null, history: f.history.filter((h) => past(h.ts)),
        feedback: f.feedback.filter((x) => past(x.ts)) } as T;
    }
    if (p === "/api/files") return e.data.files.filter((f) => past(f.created_at)).reverse().map(({ content: _c, ...rest }) => rest) as T;
    if (p === "/api/files/content") {
      const f = e.data.files.find((x) => x.path === q.get("path"));
      if (!f) throw new ApiError(404, "Datei nicht gefunden");
      return f.content as T;
    }
    throw new ApiError(404, `Nicht in der Aufzeichnung enthalten: ${p}`);
  }
}
