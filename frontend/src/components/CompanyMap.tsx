import { useMemo, useState } from "react";
import { useApp } from "../context";
import { deriveDependencies, deriveEdges, edgePath, POSITIONS, VIEW, ZONES } from "../graph";
import { COMM_KIND, STATUS, relTime } from "../labels";
import type { AgentOverview } from "../types";

function AgentNode({ a }: { a: AgentOverview }) {
  const { open, now, state } = useApp();
  const pos = POSITIONS[a.id];
  const st = STATUS[a.status];
  const running = !!state.snapshot?.active_run;
  const task = a.current_task ?? a.next_task;
  const pct = a.progress ? Math.round((a.progress.completed / a.progress.total) * 100) : null;
  return (
    <button
      className={`agent-node ${a.id === "ceo" ? "ceo" : ""} ${st.active && running ? "is-active" : ""} status-${a.status}`}
      style={{ left: `${(pos.x / VIEW.w) * 100}%`, top: `${(pos.y / VIEW.h) * 100}%`, ["--st" as string]: st.color }}
      onClick={() => open({ kind: "agent", id: a.id })}
      data-testid={`agent-${a.id}`} data-status={a.status}
      aria-label={`${a.name}, ${a.title}, Status ${st.label}`}
    >
      <div className="node-head">
        <span className="avatar" aria-hidden>{a.name.slice(0, 2)}</span>
        <div className="node-id">
          <div className="node-name">{a.name}</div>
          <div className="node-title">{a.title}</div>
        </div>
      </div>
      <div className="node-status"><span className="st-icon" aria-hidden>{st.icon}</span>{st.label}</div>
      <div className="node-task" title={task?.title}>
        {a.current_task ? <><span className="tag run">läuft</span>{a.current_task.title}</>
          : a.next_task ? <><span className="tag plan">geplant</span>{a.next_task.title}</> : <span className="muted">keine offene Aufgabe</span>}
      </div>
      <div className="node-foot">
        {pct !== null && <span className="mini-bar" title={`${a.progress!.completed}/${a.progress!.total} Aufgaben`}><i style={{ width: `${pct}%` }} /></span>}
        <span className="muted">{a.last_activity ? relTime(a.last_activity.ts, now) : "noch inaktiv"}</span>
        {a.open_approvals.length > 0 && <span className="badge warn" title="Offene Freigaben">⚑ {a.open_approvals.length}</span>}
        {a.errors.length > 0 && <span className="badge err" title="Fehler/Blockaden">! {a.errors.length}</span>}
        {a.waiting_on.length > 0 && a.status === "waiting_result" && <span className="badge" title={`Wartet auf: ${a.waiting_on.join(", ")}`}>◷ {a.waiting_on.length}</span>}
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
  const deps = useMemo(() => deriveDependencies(snap.tasks), [snap.tasks]);
  const visible = edges.filter((e) => e.active || showHistory);
  const activeCount = edges.filter((e) => e.active).length;

  return (
    <div className="map-wrap">
      <div className="map-toolbar">
        <h2>Unternehmenskarte</h2>
        <div className="legend">
          {Object.entries(COMM_KIND).map(([k, v]) => <span key={k}><i style={{ background: v.color }} />{v.label}</span>)}
          <span><i className="dashed" />Abhängigkeit</span>
        </div>
        <label className="toggle"><input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} /> bisherige Verbindungen</label>
        <label className="toggle"><input type="checkbox" checked={showDeps} onChange={(e) => setShowDeps(e.target.checked)} data-testid="toggle-deps" /> Abhängigkeiten</label>
        <span className="muted small" data-testid="active-edges">{activeCount ? `${activeCount} aktive Verbindung(en)` : "keine aktive Kommunikation"}</span>
      </div>
      <div className="map" style={{ aspectRatio: `${VIEW.w} / ${VIEW.h}` }}>
        <svg viewBox={`0 0 ${VIEW.w} ${VIEW.h}`} preserveAspectRatio="none" className="map-svg">
          <defs>
            {Object.entries(COMM_KIND).map(([k, v]) => (
              <marker key={k} id={`arrow-${k.replace(".", "-")}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill={v.color} />
              </marker>
            ))}
          </defs>
          {ZONES.map((z) => (
            <g key={z.id}>
              <rect x={z.x} y={z.y} width={z.w} height={z.h} rx={14} className={`zone zone-${z.id}`} />
              <text x={z.x + 14} y={z.labelBottom ? z.y + z.h - 10 : z.y + 20} className="zone-label">{snap.groups[z.id]}</text>
            </g>
          ))}
          {showDeps && deps.map((d) => (
            <path key={d.key} d={edgePath(d.from, d.to, -0.08)} className="dep-edge" data-testid="dep-edge">
              <title>{`Abhängigkeit (keine Kommunikation): ${d.tasks.join(", ")}`}</title>
            </path>
          ))}
          {visible.map((e) => {
            const kind = COMM_KIND[e.lastType];
            const from = e.lastEvent.from_agent!, to = e.lastEvent.to_agent!;
            const d = edgePath(from, to);
            return (
              <g key={e.key} className={`comm-edge ${e.active ? "active" : ""}`} onClick={() => open({ kind: "edge", a: e.a, b: e.b })}
                data-testid={`edge-${e.a}-${e.b}`} data-active={e.active}>
                <path d={d} className="edge-hit" />
                <path d={d} className="edge-line" stroke={kind.color} strokeWidth={Math.min(1.5 + e.count * 0.25, 4)}
                  markerEnd={e.active ? `url(#arrow-${e.lastType.replace(".", "-")})` : undefined} />
                {e.active && <path d={d} className="edge-flow" stroke={kind.color} />}
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
