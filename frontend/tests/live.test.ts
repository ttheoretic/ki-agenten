import { describe, expect, it, vi } from "vitest";
import { LiveConnection, type EventSourceLike } from "../src/live";
import type { Action } from "../src/store";

class FakeES implements EventSourceLike {
  onopen: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  listeners: Record<string, ((ev: MessageEvent) => void)[]> = {};
  closed = false;
  constructor(public url: string) {}
  addEventListener(type: string, cb: (ev: MessageEvent) => void) { (this.listeners[type] ??= []).push(cb); }
  close() { this.closed = true; }
  emit(data: unknown) { this.listeners.ev?.forEach((cb) => cb({ data: JSON.stringify(data) } as MessageEvent)); }
}

const snapshot = (last: number) => ({ last_event_id: last } as never);
const ev = (id: number) => ({ id, ts: new Date().toISOString(), type: "task.started", severity: "info", message: "x", data: {} });

function setup(apiImpl: (path: string) => Promise<unknown>) {
  const actions: Action[] = [];
  const sources: FakeES[] = [];
  const timers: (() => void)[] = [];
  const api = { get: vi.fn(apiImpl) as never, streamUrl: (id: number) => `/stream?after_id=${id}` };
  const conn = new LiveConnection({
    api, dispatch: (a) => actions.push(a), makeEventSource: (url) => { const s = new FakeES(url); sources.push(s); return s; },
    setTimer: ((fn: () => void) => { timers.push(fn); return 1; }) as never, clearTimer: (() => {}) as never, pollMs: 1e9,
  });
  return { conn, actions, sources, timers, api };
}

describe("Live-Verbindung", () => {
  it("lädt Snapshot und Ereignisse und abonniert ab der letzten ID", async () => {
    const { conn, actions, sources } = setup(async (p) => (p === "/api/state" ? snapshot(7) : [ev(6), ev(7)]));
    await conn.start();
    expect(actions.some((a) => a.type === "snapshot")).toBe(true);
    expect(sources[0].url).toBe("/stream?after_id=7");
    sources[0].onopen?.(new Event("open"));
    expect(actions.at(-1)).toEqual({ type: "conn", conn: "live" });
    conn.stop();
  });

  it("verbindet nach Abbruch neu und synchronisiert fehlende Ereignisse", async () => {
    const calls: string[] = [];
    const { conn, actions, sources, timers } = setup(async (p) => { calls.push(p); return p === "/api/state" ? snapshot(2) : p.includes("after_id=3") ? [ev(4)] : [ev(1), ev(2)]; });
    await conn.start();
    sources[0].emit(ev(3));
    sources[0].onerror?.(new Event("error"));
    expect(sources[0].closed).toBe(true);
    expect(actions.some((a) => a.type === "conn" && a.conn === "reconnecting")).toBe(true);
    const retry = timers.find(Boolean)!; // erster Timer ist die Snapshot-Aktualisierung, dann der Reconnect
    for (const t of timers.splice(0)) await t();
    expect(calls).toContain("/api/events?after_id=3&limit=2000");
    expect(sources.length).toBe(2);
    expect(sources[1].url).toBe("/stream?after_id=4");
    expect(retry).toBeTypeOf("function");
    conn.stop();
  });

  it("meldet 'offline', wenn das Backend nicht erreichbar ist", async () => {
    const { conn, actions } = setup(async () => { throw new Error("Failed to fetch"); });
    await conn.start();
    expect(actions.some((a) => a.type === "conn" && a.conn === "offline")).toBe(true);
    conn.stop();
  });
});
