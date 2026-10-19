import { useEffect, useRef, useState } from "react";
import { useApp } from "../context";
import { COMPANY_STATUS, eur, clock } from "../labels";

function ConnBadge() {
  const { state, replay } = useApp();
  if (replay) return <div className="conn conn-live" role="status" data-testid="conn-status"><span className="dot" />Wiedergabe der Aufzeichnung</div>;
  const labels = { connecting: "Verbinde …", live: "Live verbunden", reconnecting: "Verbindung unterbrochen – verbinde neu", offline: "Backend nicht erreichbar" };
  const stale = state.conn !== "live" && state.snapshotAt;
  return (
    <div className={`conn conn-${state.conn}`} role="status" data-testid="conn-status">
      <span className="dot" />
      {labels[state.conn]}
      {stale ? <span className="stale">&nbsp;· Daten veraltet (Stand {clock(new Date(state.snapshotAt!).toISOString())})</span> : null}
    </div>
  );
}

export function Header({ onOpenTab }: { onOpenTab: (tab: string) => void }) {
  const { state, api, refresh, toast, replay } = useApp();
  const [busy, setBusy] = useState<string | null>(replay ? "replay" : null);
  const [menu, setMenu] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const s = state.snapshot;

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) { setMenu(false); setConfirmStop(false); } };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [menu]);

  async function act(name: string, fn: () => Promise<unknown>, okMsg: string) {
    setBusy(name);
    setMenu(false);
    setConfirmStop(false);
    try {
      await fn();
      toast(okMsg);
      await refresh();
    } catch (e) {
      toast(`Fehlgeschlagen: ${(e as Error).message}`, "error");
    } finally {
      setBusy(replay ? "replay" : null);
    }
  }

  const status = s ? COMPANY_STATUS[s.company.status] ?? { label: s.company.status, color: "var(--muted)" } : null;
  const flags = s?.company.control ?? {};
  const running = !!s?.active_run || !!s?.server?.run_thread_busy;
  const halted = flags.paused || flags.stop_new_tasks || flags.shutdown;
  const exp = s?.experiment;
  const b = s?.budget;
  const openApprovals = s ? s.approvals.filter((a) => ["pending", "info_requested", "deferred"].includes(a.status)).length : 0;
  const apiRatio = b ? b.api_spent_eur / b.api_limit_eur : 0;

  return (
    <header className="header">
      <div className="topbar">
        <div>
          <div className="brand-name">{s?.company.name ?? "KI-Unternehmen"}</div>
          <div className="brand-sub">Control-Center{s ? ` · ${s.mode === "live" ? "Live-Betrieb" : "Dry-Run (simuliert)"}` : ""}</div>
        </div>
        {status && (
          <div className="company-status" data-testid="company-status">
            <span className="dot" style={{ background: status.color }} />{status.label}
            {s?.active_run && <span className="muted">&nbsp;· {s.active_run.agent_calls} Aufrufe</span>}
          </div>
        )}
        <ConnBadge />
        <div className="controls" ref={menuRef}>
          <button className="btn primary" disabled={!s || running || !!busy || halted}
            onClick={() => act("run", () => api.post("/api/runs"), "Geschäftslauf gestartet")} data-testid="btn-run">Lauf starten</button>
          {halted ? (
            <button className="btn" disabled={!!busy} onClick={() => act("resume", () => api.post("/api/control/resume"), "Betrieb fortgesetzt")} data-testid="btn-resume">Fortsetzen</button>
          ) : (
            <button className="btn" disabled={!!busy} onClick={() => act("pause", () => api.post("/api/control/pause"), "Unternehmen pausiert")} data-testid="btn-pause">Pausieren</button>
          )}
          <button className="btn" aria-haspopup="menu" aria-expanded={menu} disabled={!!busy} onClick={() => setMenu((m) => !m)} data-testid="btn-more">Mehr ▾</button>
          {menu && (
            <div className="menu" role="menu">
              <button role="menuitem" disabled={flags.stop_new_tasks} onClick={() => act("stop_new", () => api.post("/api/control/stop_new"), "Neue Aufgaben gestoppt")}>
                Neue Aufgaben stoppen<div className="small muted">Laufendes wird noch fertig</div></button>
              {!confirmStop ? (
                <button role="menuitem" className="danger" disabled={flags.shutdown} onClick={() => setConfirmStop(true)}>
                  Unternehmen stoppen …<div className="small muted">Bricht laufende Aufrufe kontrolliert ab</div></button>
              ) : (
                <button role="menuitem" className="danger" onClick={() => act("stop", () => api.post("/api/control/stop"), "Stopp angefordert")}>
                  Wirklich stoppen</button>
              )}
              <button role="menuitem" onClick={() => act("report", () => api.post("/api/reports"), "Statusbericht erstellt (Übersicht)")}>
                Statusbericht erstellen</button>
            </div>
          )}
        </div>
      </div>
      {s && exp && b && (
        <div className="kpis">
          <div className="kpi">
            <div className="label">Geschäftsidee</div>
            <div className="value" data-testid="selected-idea" title={s.selected_idea?.name}>
              {s.selected_idea ? s.selected_idea.name : <span className="muted">Noch nicht ausgewählt</span>}
            </div>
            <div className="sub">{s.selected_idea ? `${s.selected_idea.score} von 100 Punkten` : exp.tried_ideas.length ? `${exp.tried_ideas.length} Idee(n) verworfen` : "Recherche läuft"}</div>
          </div>
          <div className="kpi">
            <div className="label" data-testid="cycle-label">{exp.started ? `Zyklus ${exp.cycle} · Tag ${exp.day}/${exp.days}` : "Zyklus"}</div>
            <div className="value">{exp.started ? exp.work_phase.name : "Wartet auf ersten Lauf"}</div>
            <div className="phases" title={exp.cycle_label}>
              {exp.phases.map((p) => (
                <span key={p.number} style={{ flex: p.end_day - p.start_day + 1 }} title={`${p.name} (Tag ${p.start_day}–${p.end_day})`}
                  className={exp.started && exp.work_phase.number === p.number ? "current" : exp.work_phase.number > p.number ? "done" : ""} />
              ))}
            </div>
          </div>
          <div className="kpi">
            <div className="label">Fortschritt</div>
            <div className="value num" data-testid="progress">{s.progress.percent === null ? "Noch keine Daten" : `${s.progress.percent} %`}</div>
            <div className="sub">{s.progress.percent === null ? "" : `${s.progress.completed} von ${s.progress.total} Aufgaben`}</div>
          </div>
          <div className="kpi">
            <div className="label">Umsatz</div>
            <div className="value num" data-testid="revenue">{s.finance_actuals.has_revenue_data ? eur(s.finance_actuals.revenue_eur) : "Noch keine Daten"}</div>
            <div className="sub">Ausgaben {eur(s.finance_actuals.expenses_eur)}</div>
          </div>
          <div className="kpi">
            <div className="label">API-Budget{b.simulated ? " (simuliert)" : ""}</div>
            <div className="value num" data-testid="meter-api">{eur(b.api_spent_eur)} <span className="muted small">/ {eur(b.api_limit_eur, 0)}</span></div>
            <div className={`bar ${apiRatio >= 0.9 ? "err" : apiRatio >= 0.75 ? "warn" : ""}`}><i style={{ width: `${Math.min(100, apiRatio * 100)}%` }} /></div>
          </div>
          <div className={`kpi ${openApprovals ? "attention" : ""}`}>
            <div className="label">Ihre Entscheidungen</div>
            <button className="value" onClick={() => onOpenTab("approvals")}>{openApprovals ? `${openApprovals} Freigabe${openApprovals > 1 ? "n" : ""} offen` : "Keine offen"}</button>
            <div className="sub">{s.next_decision ?? "–"}</div>
          </div>
        </div>
      )}
    </header>
  );
}
