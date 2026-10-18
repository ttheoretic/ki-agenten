import { describe, expect, it } from "vitest";
import { initialState, MAX_EVENTS, mergeEvents, reducer } from "../src/store";
import type { EventItem } from "../src/types";

const ev = (id: number, type = "task.started", extra: Partial<EventItem> = {}): EventItem => ({
  id, ts: new Date(1_700_000_000_000 + id * 1000).toISOString(), type, severity: "info", agent: "research", from_agent: null,
  to_agent: null, task_id: null, run_id: null, approval_id: null, message: `e${id}`, data: {}, ...extra,
});

describe("Ereignis-Store", () => {
  it("ignoriert doppelt empfangene Ereignisse", () => {
    let s = reducer(initialState, { type: "events", events: [ev(1), ev(2)] });
    s = reducer(s, { type: "events", events: [ev(2), ev(3), ev(1)] });
    expect(s.events.map((e) => e.id)).toEqual([1, 2, 3]);
    expect(s.lastEventId).toBe(3);
  });

  it("sortiert verspätet eintreffende Ereignisse ein", () => {
    const merged = mergeEvents([ev(1), ev(5)], [ev(3)]);
    expect(merged.map((e) => e.id)).toEqual([1, 3, 5]);
  });

  it("gibt unveränderten Zustand zurück, wenn nichts Neues kommt", () => {
    const s = reducer(initialState, { type: "events", events: [ev(1)] });
    expect(reducer(s, { type: "events", events: [ev(1)] })).toBe(s);
  });

  it("begrenzt die Anzahl gehaltener Ereignisse", () => {
    const many = Array.from({ length: MAX_EVENTS + 50 }, (_, i) => ev(i + 1));
    const s = reducer(initialState, { type: "events", events: many });
    expect(s.events.length).toBe(MAX_EVENTS);
    expect(s.events[0].id).toBe(51);
  });

  it("setzt Verbindungsstatus und Fehler", () => {
    const off = reducer(initialState, { type: "conn", conn: "offline", error: "down" });
    expect(off.error).toBe("down");
    expect(reducer(off, { type: "conn", conn: "live" }).error).toBeNull();
  });
});
