import { describe, expect, it } from "vitest";
import { deriveDependencies, deriveEdges, edgePath, POSITIONS } from "../src/graph";
import type { EventItem, TaskBrief } from "../src/types";

const base = Date.parse("2026-01-01T12:00:00Z");
const ev = (id: number, type: string, from: string | null, to: string | null, secondsAgo: number): EventItem => ({
  id, ts: new Date(base - secondsAgo * 1000).toISOString(), type, severity: "info", agent: from, from_agent: from, to_agent: to,
  task_id: null, run_id: null, approval_id: null, message: `${type} ${id}`, data: {},
});

describe("Verbindungen der Unternehmenskarte", () => {
  it("entstehen nur aus Kommunikationsereignissen", () => {
    const edges = deriveEdges([
      ev(1, "task.started", "research", null, 1),
      ev(2, "file.created", "research", null, 1),
      ev(3, "comm.assignment", "ceo", "research", 1),
    ], base);
    expect(edges).toHaveLength(1);
    expect(edges[0].a).toBe("ceo");
    expect(edges[0].b).toBe("research");
  });

  it("sind nur bei frischer Kommunikation aktiv (animiert)", () => {
    const edges = deriveEdges([ev(1, "comm.handoff", "research", "strategy", 3), ev(2, "comm.feedback", "qa", "builder", 120)], base);
    const byKey = Object.fromEntries(edges.map((e) => [e.key, e]));
    expect(byKey["research|strategy"].active).toBe(true);
    expect(byKey["builder|qa"].active).toBe(false);
  });

  it("fasst beide Richtungen zusammen und merkt sich das letzte Ereignis", () => {
    const edges = deriveEdges([ev(1, "comm.feedback", "qa", "builder", 50), ev(2, "comm.handoff", "builder", "qa", 40)], base);
    expect(edges).toHaveLength(1);
    expect(edges[0].count).toBe(2);
    expect(edges[0].lastType).toBe("comm.handoff");
    expect(edges[0].directions.size).toBe(2);
  });

  it("ohne Ereignisse gibt es keine Verbindungen", () => {
    expect(deriveEdges([], base)).toEqual([]);
  });
});

describe("Abhängigkeiten", () => {
  const t = (key: string, agent: string, status: TaskBrief["status"], deps: string[] = []) =>
    ({ id: key, key, title: key, agent, status, depends_on: deps } as unknown as TaskBrief);

  it("zeigt nur offene, agentenübergreifende Abhängigkeiten", () => {
    const deps = deriveDependencies([
      t("a", "research", "completed"), t("b", "strategy", "pending", ["a"]), t("c", "strategy", "pending", ["b"]),
      t("d", "finance", "completed", ["b"]),
    ]);
    expect(deps.map((d) => d.key)).toEqual(["research>strategy"]);
  });
});

describe("Layout", () => {
  it("hat eine Position für jeden der elf Agenten", () => {
    expect(Object.keys(POSITIONS)).toHaveLength(11);
    expect(edgePath("ceo", "qa")).toMatch(/^M /);
    expect(edgePath("ceo", "unknown")).toBe("");
  });
});
