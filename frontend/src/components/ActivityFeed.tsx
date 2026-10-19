import { useMemo, useState } from "react";
import { agentName, useApp } from "../context";
import { clock, EVENT_CATEGORIES, eventCategory, SEVERITY_ORDER } from "../labels";

const RANGES: Record<string, number | null> = { all: null, "1h": 3600e3, "24h": 86400e3, "7d": 7 * 86400e3 };

export function ActivityFeed() {
  const { state, open, now } = useApp();
  const [agent, setAgent] = useState("");
  const [cat, setCat] = useState("");
  const [sev, setSev] = useState("info");
  const [range, setRange] = useState("all");
  const [more, setMore] = useState(false);
  const agents = state.snapshot?.agents ?? [];

  const items = useMemo(() => {
    const minSev = SEVERITY_ORDER.indexOf(sev);
    const since = RANGES[range] ? now - RANGES[range]! : null;
    return state.events
      .filter((e) => !agent || e.agent === agent || e.from_agent === agent || e.to_agent === agent)
      .filter((e) => !cat || eventCategory(e.type, e.data) === cat)
      .filter((e) => SEVERITY_ORDER.indexOf(e.severity) >= minSev)
      .filter((e) => !since || Date.parse(e.ts) >= since)
      .slice(-300)
      .reverse();
  }, [state.events, agent, cat, sev, range, now]);

  return (
    <div className="feed">
      <div className="section-head">
        <h2>Aktivität</h2>
        <button className="link small" style={{ marginLeft: "auto" }} onClick={() => setMore((m) => !m)} aria-expanded={more}>
          {more ? "Weniger Filter" : "Mehr Filter"}</button>
      </div>
      <div className="filters">
        <select id="feed-agent" value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent filtern">
          <option value="">Alle Agenten</option>
          {agents.map((a) => <option key={a.id} value={a.id}>{a.name} – {a.title}</option>)}
        </select>
        <select id="feed-type" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Ereignistyp filtern">
          <option value="">Alle Ereignisse</option>
          {EVENT_CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
        </select>
        {more && <>
          <select id="feed-severity" value={sev} onChange={(e) => setSev(e.target.value)} aria-label="Schweregrad filtern">
            <option value="debug">Alle Schweregrade</option>
            <option value="info">ab Info</option>
            <option value="warning">ab Warnung</option>
            <option value="error">nur Fehler</option>
          </select>
          <select id="feed-range" value={range} onChange={(e) => setRange(e.target.value)} aria-label="Zeitraum filtern">
            <option value="all">Gesamter Zeitraum</option>
            <option value="1h">Letzte Stunde</option>
            <option value="24h">Letzte 24 h</option>
            <option value="7d">Letzte 7 Tage</option>
          </select>
        </>}
      </div>
      <ol className="feed-list" data-testid="feed-list">
        {items.length === 0 && <li className="empty">Noch keine Ereignisse{state.events.length ? " für diesen Filter" : " – wartet auf ersten Lauf"}.</li>}
        {items.map((e) => (
          <li key={e.id} className={`feed-item sev-${e.severity} cat-${eventCategory(e.type, e.data)}`} onClick={() => open({ kind: "event", id: e.id })}
            data-testid="feed-item" data-event-id={e.id} title={e.type}>
            <span className="ts">{clock(e.ts)}</span>
            <div className="body">
              <div className="meta">
                {e.from_agent && e.to_agent ? `${agentName(state, e.from_agent)} → ${agentName(state, e.to_agent)}` : agentName(state, e.agent)}
              </div>
              <div className="msg">{e.message}</div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
