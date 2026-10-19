// Layout der Unternehmenskarte und Ableitung der Verbindungen aus echten Ereignissen.
import type { EventItem, TaskBrief } from "./types";

export const VIEW = { w: 1000, h: 640 };

export const POSITIONS: Record<string, { x: number; y: number }> = {
  ceo: { x: 500, y: 320 },
  research: { x: 130, y: 115 }, strategy: { x: 330, y: 115 }, finance: { x: 230, y: 230 },
  product: { x: 670, y: 115 }, builder: { x: 870, y: 115 }, qa: { x: 770, y: 230 },
  marketing: { x: 670, y: 410 }, sales: { x: 870, y: 410 }, analytics: { x: 770, y: 525 },
  operations: { x: 230, y: 470 },
};

export const ZONES: { id: string; x: number; y: number; w: number; h: number; labelBottom?: boolean }[] = [
  { id: "research_strategy", x: 30, y: 40, w: 400, h: 255 },
  { id: "product_engineering", x: 590, y: 40, w: 380, h: 255 },
  { id: "marketing_revenue", x: 610, y: 335, w: 360, h: 265, labelBottom: true },
  { id: "operations", x: 30, y: 395, w: 400, h: 150 },
  { id: "management", x: 410, y: 262, w: 180, h: 118 },
];

export const COMM_TYPES = ["comm.assignment", "comm.handoff", "comm.feedback", "comm.message", "comm.help_request", "comm.help_answer", "comm.help_offer"];

export interface Edge {
  key: string; a: string; b: string; count: number; lastTs: string; lastType: string; lastEvent: EventItem;
  directions: Set<string>; active: boolean;
}

/** Verbindungen ausschließlich aus Kommunikationsereignissen (Absender + Empfänger) – keine erfundenen Aktivitäten. */
export function deriveEdges(events: EventItem[], now = Date.now(), activeMs = 12000, windowSize = 400): Edge[] {
  const map = new Map<string, Edge>();
  const comms = events.filter((e) => COMM_TYPES.includes(e.type) && e.from_agent && e.to_agent && e.from_agent !== e.to_agent);
  for (const e of comms.slice(-windowSize)) {
    const [a, b] = [e.from_agent!, e.to_agent!].sort();
    const key = `${a}|${b}`;
    const edge = map.get(key) ?? { key, a, b, count: 0, lastTs: e.ts, lastType: e.type, lastEvent: e, directions: new Set(), active: false };
    edge.count += 1;
    edge.directions.add(`${e.from_agent}>${e.to_agent}`);
    if (e.id >= edge.lastEvent.id) { edge.lastTs = e.ts; edge.lastType = e.type; edge.lastEvent = e; }
    map.set(key, edge);
  }
  for (const edge of map.values()) edge.active = now - Date.parse(edge.lastTs) < activeMs;
  return [...map.values()];
}

export interface DepEdge { key: string; from: string; to: string; tasks: string[] }

/** Reine Abhängigkeiten offener Aufgaben (keine Kommunikation!) – werden gestrichelt und ohne Animation gezeigt. */
export function deriveDependencies(tasks: TaskBrief[]): DepEdge[] {
  const byKey = new Map(tasks.map((t) => [t.key, t]));
  const map = new Map<string, DepEdge>();
  for (const t of tasks) {
    if (t.status === "completed") continue;
    for (const d of t.depends_on) {
      const dep = byKey.get(d);
      if (!dep || dep.agent === t.agent) continue;
      const key = `${dep.agent}>${t.agent}`;
      const e = map.get(key) ?? { key, from: dep.agent, to: t.agent, tasks: [] };
      e.tasks.push(t.title);
      map.set(key, e);
    }
  }
  return [...map.values()];
}

/** Leicht gekrümmter Pfad zwischen zwei Agenten. */
export function edgePath(a: string, b: string, bend = 0.12): string {
  const p = POSITIONS[a], q = POSITIONS[b];
  if (!p || !q) return "";
  const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2;
  const dx = q.x - p.x, dy = q.y - p.y;
  const cx = mx - dy * bend, cy = my + dx * bend;
  return `M ${p.x} ${p.y} Q ${cx} ${cy} ${q.x} ${q.y}`;
}
