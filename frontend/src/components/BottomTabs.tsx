import { useEffect, useState } from "react";
import { agentName, useApp } from "../context";
import { eur, TASK_STATUS } from "../labels";
import type { TaskStatus } from "../types";
import { ApprovalCenter } from "./Approvals";

const DECISION_LABEL: Record<string, string> = { continue: "weiter im Betrieb", pivot: "Kurswechsel", stop: "neue Nische" };

const COLUMNS: TaskStatus[] = ["pending", "in_progress", "review", "blocked", "failed", "completed"];

function TasksBoard() {
  const { state, open } = useApp();
  const [agent, setAgent] = useState("");
  const current = state.snapshot!.experiment.cycle;
  const [cycle, setCycle] = useState<string>("current");
  const tasks = state.snapshot!.tasks.filter((t) => (!agent || t.agent === agent)
    && (cycle === "all" || t.cycle === (cycle === "current" ? current : Number(cycle))));
  const cycles = [...new Set(state.snapshot!.tasks.map((t) => t.cycle))].sort((a, b) => a - b);
  return (
    <div>
      <div className="filters"><select value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent">
        <option value="">Alle Agenten</option>{state.snapshot!.agents.map((a) => <option key={a.id} value={a.id}>{a.name} – {a.title}</option>)}
      </select>
      <select value={cycle} onChange={(e) => setCycle(e.target.value)} aria-label="Zyklus">
        <option value="current">Aktueller Zyklus ({current})</option><option value="all">Alle Zyklen</option>
        {cycles.map((c) => <option key={c} value={c}>Zyklus {c}</option>)}
      </select></div>
      <div className="board">
        {COLUMNS.map((c) => {
          const items = tasks.filter((t) => t.status === c);
          return (
            <div key={c} className="column" data-testid={`col-${c}`}>
              <h4 style={{ color: TASK_STATUS[c].color }}>{TASK_STATUS[c].label} <span className="muted">({items.length})</span></h4>
              {items.map((t) => (
                <div key={t.id} className="card" onClick={() => open({ kind: "task", id: t.id })}>
                  <div className="card-title">{t.title}</div>
                  <div className="small muted">{agentName(state, t.agent)} · P{t.phase}{t.revision_count ? ` · Rev. ${t.revision_count}` : ""}
                    {t.not_before_day > (state.snapshot!.experiment.day || 0) && t.status === "pending" ? ` · ab Tag ${t.not_before_day}` : ""}</div>
                  {t.error && <div className="small error">{t.error}</div>}
                </div>))}
            </div>);
        })}
      </div>
    </div>
  );
}

function Goals() {
  const { state, open, api } = useApp();
  const s = state.snapshot!;
  const [report, setReport] = useState<string | null>(null);
  useEffect(() => {
    if (!s.last_report) return;
    api.get<string>(`/api/files/content?path=${encodeURIComponent(s.last_report.path)}`).then(setReport).catch(() => setReport(null));
  }, [s.last_report?.path, api, s.last_report]);
  return (
    <div className="goals">
      <div className="col">
        <h3>Unternehmensgeschichte</h3>
        <ol className="cycles" data-testid="cycle-history">{s.experiment.cycles.map((c) => (
          <li key={c.cycle} className={c.cycle === s.experiment.cycle ? "current" : ""}>
            <b>Zyklus {c.cycle}</b> · {c.label}{c.idea ? ` · ${c.idea}` : ""}
            <div className="small muted">{new Date(c.started_at).toLocaleString("de-DE")}
              {c.decision ? ` → Entscheidung: ${DECISION_LABEL[c.decision] ?? c.decision}` : c.cycle === s.experiment.cycle ? " · läuft" : ""}</div>
          </li>))}
          {s.experiment.cycles.length === 0 && <li className="muted">Wartet auf ersten Lauf.</li>}
        </ol>
        {s.experiment.tried_ideas.length > 0 && <p className="small">Verworfene Ideen: {s.experiment.tried_ideas.join(", ")}</p>}
        <p className="small muted">Nach jeder Zyklusentscheidung plant das Unternehmen selbst den nächsten Zyklus:
          weiter → laufender Betrieb, Kurswechsel → nächstbeste Idee, Stopp → neue Nische (max. {s.experiment.max_cycles} Zyklen).</p>
        <h3>Meilensteine (aktueller Zyklus)</h3>
        <ul className="milestones">{s.milestones.map((m) => (
          <li key={m.id} className={m.achieved ? "done" : ""}><span>{m.achieved ? "✔" : "○"}</span> <b>{m.id}</b> {m.title}
            {m.achieved_at && <span className="muted small"> · {new Date(m.achieved_at).toLocaleString("de-DE")}</span>}</li>))}</ul>
        <h3>Geschäftsideen (Bewertung 0–100)</h3>
        {s.ideas.length === 0 ? <p className="muted">Noch keine Bewertung.</p> :
          <table className="table"><thead><tr><th>Idee</th><th>Punkte</th><th>Status</th></tr></thead><tbody>
            {s.ideas.map((i) => <tr key={i.id} className={i.status === "selected" ? "hl" : ""}><td>{i.name}
              <details><summary className="small">Bewertungsgrundlage</summary><ul className="bullets small">{(i.data.lines ?? []).map((l) =>
                <li key={l.label}>{l.label}: {l.points.toFixed(1)}/{l.weight} – {l.evidence}</li>)}</ul></details></td>
              <td>{i.score}</td><td>{i.status === "selected" ? "ausgewählt" : i.status === "tried" ? "versucht – verworfen" : i.status === "not_selected" ? "nicht gewählt" : "Kandidat"}</td></tr>)}
          </tbody></table>}
        <p className="small muted">Die Punktzahl ist eine Entscheidungshilfe und kein Erfolgsbeweis.</p>
      </div>
      <div className="col">
        <h3>Offene Risiken</h3>
        {s.risks.length === 0 ? <p className="muted">Keine dokumentierten Risiken.</p> :
          <ul className="risks">{s.risks.map((r, i) => <li key={i} className={`sev-${r.severity}`}><b>{r.severity}</b> {r.description}<div className="small muted">→ {r.suggested_fix}</div></li>)}</ul>}
        <h3>Blockierende Probleme</h3>
        {s.blockers.length === 0 ? <p className="muted">Keine.</p> :
          <ul className="risks">{s.blockers.map((b) => <li key={b.task_id} className="sev-error" onClick={() => open({ kind: "task", id: b.task_id })}><b>{b.title}</b> – {b.error}</li>)}</ul>}
        <h3>Nächste geplante Schritte</h3>
        {s.next_steps.length === 0 ? <p className="muted">Keine ausführbaren Aufgaben.</p> :
          <ul className="bullets">{s.next_steps.map((t) => <li key={t.id}>{t.title} <span className="muted">({agentName(state, t.agent)})</span></li>)}</ul>}
        {s.ceo_next_step && <p className="small"><b>CEO:</b> {s.ceo_next_step}</p>}
      </div>
      <div className="col">
        <h3>Letzte Entscheidungen des CEO</h3>
        {s.decisions.length === 0 ? <p className="muted">Noch keine.</p> :
          <ul className="decisions">{s.decisions.map((d) => <li key={d.id}><span className="small muted">{new Date(d.ts).toLocaleString("de-DE")}</span><div><b>{d.summary}</b></div><div className="small">{d.rationale}</div></li>)}</ul>}
        <h3>Letzter Managementbericht</h3>
        {!s.last_report ? <p className="muted">Wartet auf ersten Lauf.</p> :
          <><button className="link" onClick={() => open({ kind: "file", path: s.last_report!.path })}>{s.last_report.path}</button>
            <pre className="code report">{report ?? "Lade …"}</pre></>}
      </div>
    </div>
  );
}

function Metrics() {
  const { state, api, toast, refresh } = useApp();
  const s = state.snapshot!;
  const [form, setForm] = useState({ name: "visitors", value: "", unit: "", note: "" });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.post("/api/metrics", { ...form, value: Number(form.value) });
      toast("Kennzahl gespeichert");
      setForm({ ...form, value: "", note: "" });
      await refresh();
    } catch (err) { toast(String((err as Error).message), "error"); }
  }
  return (
    <div className="metrics">
      <div className="col">
        <h3>Gemessene Kennzahlen</h3>
        {s.metrics.length === 0 ? <p className="muted" data-testid="no-metrics">Noch keine Daten. Kennzahlen stammen ausschließlich aus echten Messungen.</p> :
          <table className="table"><thead><tr><th>Zeit</th><th>Kennzahl</th><th>Wert</th><th>Quelle</th></tr></thead><tbody>
            {s.metrics.map((m) => <tr key={m.id}><td>{new Date(m.ts).toLocaleString("de-DE")}</td><td>{m.name}</td><td>{m.value} {m.unit}</td><td>{m.source}</td></tr>)}
          </tbody></table>}
      </div>
      <div className="col">
        <h3>Echten Messwert erfassen</h3>
        <form className="metric-form" onSubmit={submit}>
          <select value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="Kennzahl">
            {["visitors", "inquiries", "signups", "sales", "revenue_eur", "conversion_rate", "ad_spend_eur"].map((n) => <option key={n}>{n}</option>)}
          </select>
          <input required type="number" step="any" placeholder="Wert" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} aria-label="Wert" />
          <input placeholder="Einheit" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} aria-label="Einheit" />
          <input placeholder="Quelle/Notiz (z. B. Hosting-Statistik)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} aria-label="Notiz" />
          <button className="btn primary">Speichern</button>
        </form>
        <p className="small muted">Analytics wertet nur diese Werte aus; erfundene Kennzahlen werden vom Programm abgewiesen.</p>
      </div>
    </div>
  );
}

function Costs() {
  const { state } = useApp();
  const s = state.snapshot!;
  const b = s.budget;
  const max = Math.max(0.000001, ...s.agents.map((a) => a.cost_eur));
  return (
    <div className="costs">
      <div className="col">
        <h3>Budget {b.month}{b.simulated && " (simulierte Kosten)"}</h3>
        <table className="kv"><tbody>
          <tr><td>API-Kosten</td><td>{eur(b.api_spent_eur, 4)} / {eur(b.api_limit_eur)}</td></tr>
          <tr><td>Externe Ausgaben</td><td>{eur(b.external_spent_eur)} (gebunden durch Freigaben: {eur(b.external_committed_eur)})</td></tr>
          <tr><td>Gesamt verbleibend</td><td>{eur(b.total_remaining_eur)} von {eur(b.total_limit_eur)}</td></tr>
          <tr><td>Limit pro Lauf</td><td>{eur(b.per_run_limit_eur)} · max. {b.max_calls_per_run} Agentenaufrufe</td></tr>
          <tr><td>Davon geschätzt</td><td>{eur(b.estimated_share_eur, 4)} (Verbrauch nicht exakt bekannt, konservativ)</td></tr>
        </tbody></table>
        <p className="small muted">Warnungen bei 50/75/90 %, automatischer Stopp bei 100 %. Ein App-Limit ersetzt kein Ausgabenlimit im Anbieterkonto.</p>
      </div>
      <div className="col">
        <h3>API-Kosten pro Agent</h3>
        <ul className="bars">{[...s.agents].sort((x, y) => y.cost_eur - x.cost_eur).map((a) => (
          <li key={a.id}><span className="bar-label">{a.name}</span><span className="bar"><i style={{ width: `${(a.cost_eur / max) * 100}%` }} /></span>
            <span className="small">{eur(a.cost_eur, 4)} · {a.calls} Aufrufe · {a.model}</span></li>))}</ul>
      </div>
    </div>
  );
}

function Files() {
  const { api, open, state } = useApp();
  const [files, setFiles] = useState<{ path: string; agent: string; size: number; created_at: string; kind: string }[]>([]);
  useEffect(() => { api.get<typeof files>("/api/files").then(setFiles).catch(() => setFiles([])); }, [api, state.lastEventId]);
  return files.length === 0 ? <p className="muted">Noch keine Dateien erzeugt.</p> : (
    <table className="table"><thead><tr><th>Datei</th><th>Agent</th><th>Art</th><th>Größe</th><th>Erstellt</th></tr></thead><tbody>
      {files.map((f) => <tr key={f.path} onClick={() => open({ kind: "file", path: f.path })} className="clickable">
        <td>{f.path}</td><td>{agentName(state, f.agent)}</td><td>{f.kind}</td><td>{(f.size / 1024).toFixed(1)} KB</td><td>{new Date(f.created_at).toLocaleString("de-DE")}</td></tr>)}
    </tbody></table>
  );
}

export function BottomTabs() {
  const { state } = useApp();
  const s = state.snapshot!;
  const openApprovals = s.approvals.filter((a) => ["pending", "info_requested", "deferred"].includes(a.status)).length;
  const tabs = [
    { id: "approvals", label: "Freigaben", badge: openApprovals },
    { id: "goals", label: "Ziele & Meilensteine" },
    { id: "tasks", label: "Aufgaben", badge: s.blockers.length || undefined },
    { id: "metrics", label: "Kennzahlen" },
    { id: "costs", label: "Kosten" },
    { id: "files", label: "Dateien & Ergebnisse" },
  ];
  const [tab, setTab] = useState(openApprovals ? "approvals" : "goals");
  return (
    <section className="bottom">
      <nav className="tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}>
            {t.label}{t.badge ? <span className="badge warn">{t.badge}</span> : null}
          </button>))}
      </nav>
      <div className="tab-body">
        {tab === "approvals" && <ApprovalCenter />}
        {tab === "goals" && <Goals />}
        {tab === "tasks" && <TasksBoard />}
        {tab === "metrics" && <Metrics />}
        {tab === "costs" && <Costs />}
        {tab === "files" && <Files />}
      </div>
    </section>
  );
}
