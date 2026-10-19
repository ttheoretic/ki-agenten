import { useMemo, useState } from "react";
import { useApp } from "../context";
import { deriveDependencies, deriveEdges, edgePath, POSITIONS, VIEW, ZONES } from "../graph";
import { COMM_KIND, STATUS } from "../labels";
import type { AgentOverview } from "../types";

function AgentNode({ a }: { a: AgentOverview }) {
  const { open, state } = useApp();
  const pos = POSITIONS[a.id];
  const st = STATUS[a.status];
  const running = !!state.snapshot?.active_run;
  const task = a.current_task ?? a.next_task;
  const flags = a.open_approvals.length + a.errors.length;
  return (
    <button
      className={`agent-node ${a.id === "ceo" ? "ceo" : ""} ${st.active && running ? "is-active" : ""} status-${a.status}`}
      style={{ left: `${(pos.x / VIEW.w) * 100}%`, top: `${(pos.y / VIEW.h) * 100}%`, ["--st" as string]: st.color }}
      onClick={() => open({ kind: "agent", id: a.id })}
      data-testid={`agent-${a.id}`} data-status={a.status}
      aria-label={`${a.name}, ${a.title}, Status ${st.label}`}
      title={`${a.title}${task ? ` – ${task.title}` : ""}`}
    >
      <div className="node-head">
        <span className="node-name">{a.name}</span>
        <span className="node-title">{a.title.split(" / ")[0].split(" & ")[0]}</span>
      </div>
      <div className="node-status">
        <span className="dot" />{st.label}
        {flags > 0 && <span className={`badge ${a.errors.length ? "err" : "warn"}`}>{flags}</span>}
      </div>
      <div className={`node-task ${a.current_task ? "running" : ""}`}>
        {a.current_task ? a.current_task.title : a.next_task ? `Als Nächstes: ${a.next_task.title}` : "—"}
      </div>
    </button>
  );
}

export function CompanyMap() {
  const { state, open, now } = useApp();
  const [showDeps, setShowDeps] = useState(false);
  const [showHistory, setShowHistory] = useState(true);
  const snap = state.snapshot!;
  const edges = useMemo(() => deriveEdges(state.events, now), [state.events, now]);
  const deps = useMemo(() => deriveDependencies(snap.tasks.filter((t) => t.cycle === snap.experiment.cycle)), [snap.tasks, snap.experiment.cycle]);
  const visible = edges.filter((e) => e.active || showHistory);
  const activeCount = edges.filter((e) => e.active).length;
  const legend = [["comm.assignment", "Auftrag"], ["comm.handoff", "Übergabe"], ["comm.feedback", "Rückgabe"], ["comm.help_answer", "Teamhilfe"]];

  return (
    <div className="map-wrap">
      <div className="section-head">
        <h2>Team</h2>
        <div className="legend">
          {legend.map(([k, l]) => <span key={k}><i style={{ borderColor: COMM_KIND[k].color }} />{l}</span>)}
          {showDeps && <span><i className="dashed" style={{ borderColor: "var(--muted)" }} />Abhängigkeit</span>}
        </div>
        <div className="map-tools">
          <span className="muted small" data-testid="active-edges">{activeCount ? `${activeCount} aktive Verbindung${activeCount > 1 ? "en" : ""}` : "keine aktive Kommunikation"}</span>
          <label className="toggle"><input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} /> Verlauf</label>
          <label className="toggle"><input type="checkbox" checked={showDeps} onChange={(e) => setShowDeps(e.target.checked)} data-testid="toggle-deps" /> Abhängigkeiten</label>
        </div>
      </div>
      <div className="map" style={{ aspectRatio: `${VIEW.w} / ${VIEW.h}` }}>
        <svg viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} preserveAspectRatio="none" className="map-svg">
          <defs>
            {Object.entries(COMM_KIND).map(([k, v]) => (
              <marker key={k} id={`arrow-${k.replace(".", "-")}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" style={{ fill: v.color }} />
              </marker>
            ))}
          </defs>
          {ZONES.filter((z) => z.id !== "management").map((z) => (
            <text key={z.id} x={z.x + 6} y={z.labelBottom ? z.y + z.h - 6 : z.y + 14} className="zone-label">{snap.groups[z.id]}</text>
          ))}
          {showDeps && deps.map((d) => (
            <path key={d.key} d={edgePath(d.from, d.to, -0.08)} className="dep-edge" data-testid="dep-edge">
              <title>{`Abhängigkeit (keine Kommunikation): ${d.tasks.join(", ")}`}</title>
            </path>
          ))}
          {visible.map((e) => {
            const kind = COMM_KIND[e.lastType];
            const d = edgePath(e.lastEvent.from_agent!, e.lastEvent.to_agent!);
            return (
              <g key={e.key} className={`comm-edge ${e.active ? "active" : ""}`} onClick={() => open({ kind: "edge", a: e.a, b: e.b })}
                data-testid={`edge-${e.a}-${e.b}`} data-active={e.active}>
                <path d={d} className="edge-hit" />
                <path d={d} className="edge-line" style={{ stroke: e.active ? kind.color : "var(--line-strong)", strokeWidth: e.active ? 2 : 1,
                  strokeDasharray: kind.dashed ? "4 4" : undefined }}
                  markerEnd={e.active ? `url(#arrow-${e.lastType.replace(".", "-")})` : undefined} />
                {e.active && <path d={d} className="edge-flow" style={{ stroke: kind.color }} />}
                <title>{`${kind.label}: ${e.lastEvent.message} (${e.count} Ereignisse) – klicken für Details`}</title>
              </g>
            );
          })}
        </svg>
        {snap.agents.map((a) => <AgentNode key={a.id} a={a} />)}
      </div>
    </div>
  );
}
