import { createContext, useContext } from "react";
import type { ApiLike } from "./replay";
import type { State } from "./store";

export type Panel =
  | { kind: "agent"; id: string }
  | { kind: "edge"; a: string; b: string }
  | { kind: "event"; id: number }
  | { kind: "file"; path: string }
  | { kind: "task"; id: string };

export interface Ctx {
  api: ApiLike;
  state: State;
  refresh: () => Promise<void>;
  open: (p: Panel) => void;
  toast: (msg: string, kind?: "ok" | "error") => void;
  now: number;
  replay?: boolean;
}

export const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const c = useContext(AppContext);
  if (!c) throw new Error("AppContext fehlt");
  return c;
}

export function agentName(state: State, id: string | null | undefined): string {
  if (!id) return "System";
  const a = state.snapshot?.agents.find((x) => x.id === id);
  return a ? a.name : id;
}
