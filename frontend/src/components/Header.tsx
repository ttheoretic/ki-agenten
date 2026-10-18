import { useState } from "react";
import { useApp } from "../context";
import { COMPANY_STATUS, eur, clock } from "../labels";

function ConnBadge() {
  const { state } = useApp();
  const labels = { connecting: "Verbinde …", live: "Live verbunden", reconnecting: "Verbindung unterbrochen – verbinde neu", offline: "Backend nicht erreichbar" };
  const stale = state.conn !== "live" && state.snapshotAt;
  return (
    <div className={`conn conn-${state.conn}`} role="status" data-testid="conn-status">
      <span className="dot" />
      {labels[state.conn]}
      {stale ? <span className="stale"> · Daten veraltet (Stand {clock(new Date(state.snapshotAt!).toISOString())})</span> : null}
    </div>
  );
}

function Meter({ label, value, limit, testid }: { label: string; value: number; limit: number; testid?: string }) {
  const ratio = limit > 0 ? Math.min(1, value / limit) : 0;
  const color = ratio >= 0.9 ? "#ef4444" : ratio >= 0.75 ? "#f59e0b" : ratio >= 0.5 ? "#eab308" : "#22c55e";
  return (
    <div className="meter" data-testid={testid}>
      <div className="meter-head"><span>{label}</span><b>{eur(value)} / {eur(limit)}</b></div>
      <div className="meter-bar"><div style={{ width: `${ratio * 100}%`, background: color }} /></div>
    </div>
  );
}

export function Header() {
  const { state, api, refresh, toast } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const s = state.snapshot;

  async function act(name: string, fn: () => Promise<unknown>, okMsg: string) {
    setBusy(name);
    try {
      await fn();
      toast(okMsg);
      await refresh();
    } catch (e) {
      toast(`Fehlgeschlagen: ${(e as Error).message}`, "error");
    } finally {
      setBusy(null);
    }
  }

  const status = s ? COMPANY_STATUS[s.company.status] ?? { label: s.company.status, color: "#94a3b8" } : null;
  const flags = s?.company.control ?? {};
  const running = !!s?.active_run || !!s?.server?.run_thread_busy;
  const exp = s?.experiment;

  return (
    <header className="header">
      <div className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>◎</span>
          <div>
            <div className="brand-name">{s?.company.name ?? "KI-Unternehmen"}</div>
            <div className="brand-sub">Live-Control-Center · {s?.mode_label ?? "…"}</div>
          </div>
        </div>
        {status && (
          <div className="company-status" style={{ borderColor: status.color }} data-testid="company-status">
            <span className="dot" style={{ background: status.color }} />{status.label}
            {s?.active_run && <span className="muted"> · {s.active_run.agent_calls} Aufrufe</span>}
          </div>
        )}
        <ConnBadge />
        <div className="controls">
          <button className="btn primary" disabled={!s || running || !!busy || flags.paused || flags.stop_new_tasks}
            onClick={() => act("run", () => api.post("/api/runs"), "Geschäftslauf gestartet")} data-testid="btn-run">
            ▶ Lauf starten
          </button>
          {flags.paused || flags.stop_new_tasks || flags.shutdown ? (
            <button className="btn" disabled={!!busy} onClick={() => act("resume", () => api.post("/api/control/resume"), "Betrieb fortgesetzt")} data-testid="btn-resume">⟲ Fortsetzen</button>
          ) : (
            <button className="btn" disabled={!!busy} onClick={() => act("pause", () => api.post("/api/control/pause"), "Unternehmen pausiert")} data-testid="btn-pause">❚❚ Pausieren</button>
          )}
          <button className="btn" disabled={!!busy || flags.stop_new_tasks} title="Laufende Aufgaben werden geordnet abgeschlossen, keine neuen gestartet"
            onClick={() => act("stop_new", () => api.post("/api/control/stop_new"), "Neue Aufgaben gestoppt")}>⏹ Neue Aufgaben stoppen</button>
          <button className="btn danger" disabled={!!busy || flags.shutdown} title="Laufende Aufrufe kontrolliert abbrechen, keine externen Aktionen"
            onClick={() => { if (confirm("Unternehmen stoppen? Laufende Agentenaufrufe werden kontrolliert abgebrochen.")) void act("stop", () => api.post("/api/control/stop"), "Stopp angefordert"); }}>■ Stopp</button>
          <button className="btn ghost" disabled={!!busy} onClick={() => act("report", () => api.post("/api/reports"), "Statusbericht erstellt (siehe Berichte)")}>⎙ Statusbericht</button>
        </div>
      </div>
      {s && exp && (
        <div className="mission">
          <div className="mission-goal">
            <div className="label">Unternehmensziel</div>
            <div className="goal-text">{s.company.goal}</div>
            <div className="label" style={{ marginTop: 8 }}>Geschäftsmodell</div>
            <div className="idea" data-testid="selected-idea">
              {s.selected_idea ? <><b>{s.selected_idea.name}</b> <span className="pill">{s.selected_idea.score} Punkte</span></> : <span className="muted">Noch nicht ausgewählt</span>}
            </div>
          </div>
          <div className="mission-timeline">
            <div className="label">30-Tage-Experiment · {exp.started ? `Tag ${exp.day}/${exp.days}` : "Wartet auf ersten Lauf"}
              {exp.clock === "accelerated" && <span className="muted"> (beschleunigte Dry-Run-Uhr)</span>}</div>
            <div className="timeline">
              {exp.phases.map((p) => {
                const isWork = exp.work_phase.number === p.number && exp.started;
                return (
                  <div key={p.number} className={`phase ${isWork ? "current" : ""} ${exp.work_phase.number > p.number ? "done" : ""}`}
                    style={{ flex: p.end_day - p.start_day + 1 }} title={p.goal}>
                    <span>P{p.number} {p.name}</span><small>Tag {p.start_day}–{p.end_day}</small>
                  </div>
                );
              })}
              {exp.started && <div className="day-marker" style={{ left: `${((exp.day - 0.5) / exp.days) * 100}%` }} title={`Tag ${exp.day}`} />}
            </div>
            <div className="mission-row">
              <div><div className="label">Arbeitsphase</div><b>{exp.work_phase.name}</b></div>
              <div><div className="label">Fortschritt</div>
                <b data-testid="progress">{s.progress.percent === null ? "Noch keine Daten" : `${s.progress.completed}/${s.progress.total} Aufgaben (${s.progress.percent} %)`}</b></div>
              <div><div className="label">Nächste Entscheidung</div><b>{s.next_decision ?? "–"}</b></div>
            </div>
          </div>
          <div className="mission-budget">
            <Meter label={`API-Kosten ${s.budget.simulated ? "(simuliert)" : ""}`} value={s.budget.api_spent_eur} limit={s.budget.api_limit_eur} testid="meter-api" />
            <Meter label="Gesamtbudget" value={s.budget.total_spent_eur + s.budget.external_committed_eur} limit={s.budget.total_limit_eur} />
            <div className="mission-row small">
              <div><div className="label">Einnahmen</div><b data-testid="revenue">{s.finance_actuals.has_revenue_data ? eur(s.finance_actuals.revenue_eur) : "Noch keine Daten"}</b></div>
              <div><div className="label">Ausgaben</div><b>{eur(s.finance_actuals.expenses_eur)}</b></div>
              <div><div className="label">Verbleibend</div><b>{eur(s.budget.total_remaining_eur)}</b></div>
            </div>
            {s.last_run && <div className="muted small">Letzter Lauf: {s.last_run.stop_reason ?? s.last_run.status}</div>}
          </div>
        </div>
      )}
    </header>
  );
}
