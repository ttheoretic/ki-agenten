// Zustand des Control-Centers: Backend-Snapshot + deduplizierter Ereignisstrom.
import type { ConnState, EventItem, Snapshot } from "./types";

export const MAX_EVENTS = 1500;

export interface State {
  snapshot: Snapshot | null;
  snapshotAt: number | null;
  events: EventItem[];
  lastEventId: number;
  conn: ConnState;
  error: string | null;
}

export type Action =
  | { type: "snapshot"; snapshot: Snapshot; at: number }
  | { type: "events"; events: EventItem[] }
  | { type: "conn"; conn: ConnState; error?: string | null };

export const initialState: State = { snapshot: null, snapshotAt: null, events: [], lastEventId: 0, conn: "connecting", error: null };

/** Fügt Ereignisse ein; doppelt empfangene IDs werden ignoriert, Reihenfolge nach ID. */
export function mergeEvents(existing: EventItem[], incoming: EventItem[]): EventItem[] {
  if (!incoming.length) return existing;
  const seen = new Set(existing.map((e) => e.id));
  const fresh = incoming.filter((e) => !seen.has(e.id) && (seen.add(e.id), true));
  if (!fresh.length) return existing;
  const lastId = existing.length ? existing[existing.length - 1].id : 0;
  const merged = fresh.every((e) => e.id > lastId) ? existing.concat(fresh.sort((a, b) => a.id - b.id))
    : existing.concat(fresh).sort((a, b) => a.id - b.id);
  return merged.length > MAX_EVENTS ? merged.slice(merged.length - MAX_EVENTS) : merged;
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "snapshot":
      return { ...state, snapshot: action.snapshot, snapshotAt: action.at, error: null };
    case "events": {
      const events = mergeEvents(state.events, action.events);
      if (events === state.events) return state;
      return { ...state, events, lastEventId: Math.max(state.lastEventId, events[events.length - 1]?.id ?? 0) };
    }
    case "conn":
      return { ...state, conn: action.conn, error: action.error ?? (action.conn === "live" ? null : state.error) };
  }
}
