import { useEffect, useState } from "react";
import { agentName, useApp } from "../context";
import { eur, TASK_STATUS } from "../labels";
import type { TaskStatus } from "../types";
import { ApprovalCenter } from "./Approvals";

const DECISION_LABEL: Record<string, string> = { continue: "weiter im Betrieb", pivot: "Kurswechsel", stop: "neue Nische" };
const COLUMNS: TaskStatus[] = ["pending", "in_progress", "review", "blocked", "failed", "completed"];
const IDEA_STATUS: Record<string, string> = { selected: "ausgewählt", tried: "versucht – verworfen", not_selected: "nicht gewählt", candidate: "Kandidat" };

function Overview() {
  const { state, open, api } = useApp();
  const s = state.snapshot!;
  const exp = s.experiment;
  const [report, setReport] = useState<string | null>(null);
  useEffect(() => {
    if (!s.last_report) return;
    api.get<string>(`/api/files/content?path=${encodeURIComponent(s.last_report.path)}`).then(setReport).catch(() => setReport(null));
  }, [s.last_report?.path, api, s.last_report]);
  return (
    <div className="grid3">
      <section>
        <h3 style={{ marginTop: 0 }}>Ziel</h3>
        <p className="goal">{s.company.goal}</p>
        <h3>Verlauf des Unternehmens</h3>
        <ol className="plain cycles" data-testid="cycle-history">
          {exp.cycles.map((c) => (
            <li key={c.cycle} className={c.cycle === exp.cycle ? "current" : ""}>
              <b>Zyklus {c.cycle}</b> · {c.label}{c.idea ? ` · ${c.idea}` : ""}
              <div className="small muted">{new Date(c.started_at).toLocaleDateString("de-DE")}
                {c.decision ? ` · Entscheidung: ${DECISION_LABEL[c.decision] ?? c.decision}` : c.cycle === exp.cycle ? " · läuft" : ""}</div>
            </li>))}
          {exp.cycles.length === 0 && <li className="muted">Wartet auf ersten Lauf.</li>}
        </ol>
        <p className="small muted">Nach jeder Zyklusentscheidung plant das Team den nächsten Zyklus selbst: weiter, Kurswechsel zur
          nächstbesten Idee oder neue Nische (höchstens {exp.max_cycles} Zyklen).</p>
        <h3>Meilensteine dieses Zyklus</h3>
        <ul className="plain milestones">{s.milestones.map((m) => (
          <li key={m.id} className={m.achieved ? "done" : ""}><span className="mark">{m.achieved ? "✓" : "○"}</span>{m.title}
            {m.achieved_at && <span className="muted small"> · {new Date(m.achieved_at).toLocaleString("de-DE")}</span>}</li>))}</ul>
      </section>
      <section>
        <h3 style={{ marginTop: 0 }}>Letzte Entscheidungen des CEO</h3>
        {s.decisions.length === 0 ? <p className="muted">Noch keine.</p> :
          <ul className="plain">{s.decisions.slice(0, 5).map((d) => (
            <li key={d.id}><div>{d.summary}</div><div className="small muted">{new Date(d.ts).toLocaleString("de-DE")} · {d.rationale}</div></li>))}</ul>}
        <h3>Offene Risiken</h3>
        {s.risks.length === 0 ? <p className="muted">Keine dokumentierten Risiken.</p> :
          <ul className="plain">{s.risks.slice(0, 6).map((r, i) => (
            <li key={i}><span className={`sev ${r.severity}`}>{r.severity}</span>{r.description}<div className="small muted">→ {r.suggested_fix}</div></li>))}</ul>}
        {s.blockers.length > 0 && <>
          <h3>Blockaden</h3>
          <ul className="plain">{s.blockers.map((b) => (
            <li key={b.task_id}><button className="link" onClick={() => open({ kind: "task", id: b.task_id })}>{b.title}</button>
              <div className="small error">{b.error}</div></li>))}</ul></>}
        <h3>Als Nächstes</h3>
        {s.next_steps.length === 0 ? <p className="muted">Keine ausführbaren Aufgaben.</p> :
          <ul className="plain">{s.next_steps.map((t) => <li key={t.id}>{t.title} <span className="muted">· {agentName(state, t.agent)}</span></li>)}</ul>}
      </section>
      <section>
        <h3 style={{ marginTop: 0 }}>Geschäftsideen (0–100 Punkte)</h3>
        {s.ideas.length === 0 ? <p className="muted">Noch keine Bewertung.</p> : (
          <div className="scroll-x"><table className="table"><thead><tr><th>Idee</th><th className="num">Punkte</th><th>Status</th></tr></thead><tbody>
            {s.ideas.map((i) => <tr key={i.id} className={i.status === "selected" ? "hl" : ""}><td>{i.name}
              <details><summary className="small">Bewertungsgrundlage</summary><ul className="bullets small">{(i.data.lines ?? []).map((l) =>
                <li key={l.label}>{l.label}: {l.points.toFixed(1)}/{l.weight} – {l.evidence}</li>)}</ul></details></td>
              <td className="num">{i.score}</td><td>{IDEA_STATUS[i.status] ?? i.status}</td></tr>)}
          </tbody></table></div>)}
        <h3>Letzter Bericht</h3>
        {!s.last_report ? <p className="muted">Wartet auf ersten Lauf.</p> :
          <><button className="link small" onClick={() => open({ kind: "file", path: s.last_report!.path })}>Vollständig öffnen</button>
            <pre className="code report">{report ?? "Lade …"}</pre></>}
      </section>
    </div>
  );
}

function Team() {
  const { state, open } = useApp();
  const s = state.snapshot!;
  const helps = s.tasks.filter((t) => t.kind === "consultation").sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1));
  const answers = new Map(state.events.filter((e) => e.type === "comm.help_answer" && e.task_id).map((e) => [e.task_id!, e.message]));
  return (
    <div>
      <p className="small muted" style={{ marginTop: 0 }}>Wenn einem Agenten Fachwissen fehlt, fragt er einen Kollegen. Wartet sein Ergebnis auf die Antwort,
        pausiert er die Aufgabe, bis sie da ist. Wird Arbeit zurückgegeben, bietet ein passender Kollege von sich aus Hilfe an.
        Die Antworten fließen in die weitere Arbeit ein.</p>
      {helps.length === 0 ? <p className="muted" data-testid="no-teamwork">Noch keine Zusammenarbeit protokolliert.</p> : (
        <div data-testid="teamwork">{helps.map((t) => {
          const offer = t.title.startsWith("Hilfe angeboten");
          return (
            <div key={t.id} className="team-row">
              <div>
                <div className="team-kind">{offer ? "Bietet Hilfe an" : "Hilfeanfrage"}</div>
                <div className="team-who">{offer ? `${agentName(state, t.agent)} hilft ${agentName(state, t.created_by)}`
                  : `${agentName(state, t.created_by)} fragt ${agentName(state, t.agent)}`}</div>
              </div>
              <div>
                <button className="link" onClick={() => open({ kind: "task", id: t.id })}>{t.title.replace(/^Hilfe( angeboten)? für [^:]+: /, "")}</button>
                {answers.get(t.id) && <div className="small muted">{answers.get(t.id)}</div>}
              </div>
              <div className="small" style={{ color: TASK_STATUS[t.status].color }}>{t.status === "completed" ? "beantwortet" : TASK_STATUS[t.status].label}</div>
            </div>
          );
        })}</div>)}
    </div>
  );
}

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
      <div className="filters" style={{ padding: "0 0 12px", border: "none" }}>
        <select id="tasks-agent" value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent">
          <option value="">Alle Agenten</option>{state.snapshot!.agents.map((a) => <option key={a.id} value={a.id}>{a.name} – {a.title}</option>)}
        </select>
        <select id="tasks-cycle" value={cycle} onChange={(e) => setCycle(e.target.value)} aria-label="Zyklus">
          <option value="current">Aktueller Zyklus ({current})</option><option value="all">Alle Zyklen</option>
          {cycles.map((c) => <option key={c} value={c}>Zyklus {c}</option>)}
        </select>
      </div>
      <div className="board">
        {COLUMNS.map((c) => {
          const items = tasks.filter((t) => t.status === c);
          return (
            <div key={c} className="column" data-testid={`col-${c}`}>
              <h4>{TASK_STATUS[c].label} <span className="muted">{items.length}</span></h4>
              {items.map((t) => (
                <div key={t.id} className="card" onClick={() => open({ kind: "task", id: t.id })}>
                  <div className="card-title">{t.title}</div>
                  <div className="small muted">{agentName(state, t.agent)}{t.revision_count ? ` · Überarbeitung ${t.revision_count}` : ""}
                    {t.not_before_day > (state.snapshot!.experiment.day || 0) && t.status === "pending" ? ` · ab Tag ${t.not_before_day}` : ""}</div>
                  {t.error && <div className="small error">{t.error}</div>}
                </div>))}
            </div>);
        })}
      </div>
    </div>
  );
}

function Metrics() {
  const { state, api, toast, refresh, replay } = useApp();
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
    <div className="grid3">
      <section style={{ gridColumn: "span 2" }}>
        <h3 style={{ marginTop: 0 }}>Gemessene Kennzahlen</h3>
        {s.metrics.length === 0 ? <p className="muted" data-testid="no-metrics">Noch keine Daten. Kennzahlen stammen ausschließlich aus echten Messungen.</p> : (
          <div className="scroll-x"><table className="table"><thead><tr><th>Zeit</th><th>Kennzahl</th><th className="num">Wert</th><th>Quelle</th><th>Notiz</th></tr></thead><tbody>
            {s.metrics.map((m) => <tr key={m.id}><td>{new Date(m.ts).toLocaleString("de-DE")}</td><td>{m.name}</td>
              <td className="num">{m.value} {m.unit}</td><td>{m.source}</td><td className="muted">{m.note}</td></tr>)}
          </tbody></table></div>)}
      </section>
      <section>
        <h3 style={{ marginTop: 0 }}>Messwert erfassen</h3>
        <form className="metric-form" onSubmit={submit}>
          <select id="metric-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="Kennzahl">
            {["visitors", "inquiries", "signups", "sales", "revenue_eur", "conversion_rate", "ad_spend_eur"].map((n) => <option key={n}>{n}</option>)}
          </select>
          <input id="metric-value" required type="number" step="any" placeholder="Wert" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} aria-label="Wert" />
          <input id="metric-note" placeholder="Quelle (z. B. Hosting-Statistik)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} aria-label="Notiz" />
          <button className="btn primary" disabled={replay}>Speichern</button>
        </form>
        <p className="small muted">Analytics wertet nur diese Werte aus; erfundene Kennzahlen werden vom Programm abgewiesen.</p>
      </section>
    </div>
  );
}

function Costs() {
  const { state } = useApp();
  const s = state.snapshot!;
  const b = s.budget;
  const max = Math.max(0.000001, ...s.agents.map((a) => a.cost_eur));
  return (
    <div className="grid3">
      <section>
        <h3 style={{ marginTop: 0 }}>Budget {b.month}{b.simulated && " (simuliert)"}</h3>
        <table className="kv"><tbody>
          <tr><td>API-Kosten</td><td className="num">{eur(b.api_spent_eur, 4)} von {eur(b.api_limit_eur)}</td></tr>
          <tr><td>Externe Ausgaben</td><td className="num">{eur(b.external_spent_eur)} (gebunden: {eur(b.external_committed_eur)})</td></tr>
          <tr><td>Gesamt verbleibend</td><td className="num">{eur(b.total_remaining_eur)} von {eur(b.total_limit_eur)}</td></tr>
          <tr><td>Grenze pro Lauf</td><td className="num">{eur(b.per_run_limit_eur)} · max. {b.max_calls_per_run} Aufrufe</td></tr>
          <tr><td>Davon geschätzt</td><td className="num">{eur(b.estimated_share_eur, 4)}</td></tr>
        </tbody></table>
        <p className="small muted">Warnungen bei 50, 75 und 90 %, automatischer Stopp bei 100 %.</p>
      </section>
      <section style={{ gridColumn: "span 2" }}>
        <h3 style={{ marginTop: 0 }}>API-Kosten pro Agent</h3>
        <ul className="bars">{[...s.agents].sort((x, y) => y.cost_eur - x.cost_eur).map((a) => (
          <li key={a.id}><span>{a.name}</span><span className="bar"><i style={{ width: `${(a.cost_eur / max) * 100}%` }} /></span>
            <span className="num muted">{eur(a.cost_eur, 4)} · {a.calls} Aufrufe</span></li>))}</ul>
      </section>
    </div>
  );
}

function Files() {
  const { api, open, state } = useApp();
  const [files, setFiles] = useState<{ path: string; agent: string; size: number; created_at: string; kind: string }[]>([]);
  useEffect(() => { api.get<typeof files>("/api/files").then(setFiles).catch(() => setFiles([])); }, [api, state.lastEventId]);
  return files.length === 0 ? <p className="muted">Noch keine Dateien erzeugt.</p> : (
    <div className="scroll-x"><table className="table"><thead><tr><th>Datei</th><th>Agent</th><th className="num">Größe</th><th>Erstellt</th></tr></thead><tbody>
      {files.map((f) => <tr key={f.path} onClick={() => open({ kind: "file", path: f.path })} className="clickable">
        <td>{f.path}</td><td>{agentName(state, f.agent)}</td><td className="num">{(f.size / 1024).toFixed(1)} KB</td>
        <td>{new Date(f.created_at).toLocaleString("de-DE")}</td></tr>)}
    </tbody></table></div>
  );
}

export function BottomTabs({ tab, setTab }: { tab: string; setTab: (t: string) => void }) {
  const { state } = useApp();
  const s = state.snapshot!;
  const openApprovals = s.approvals.filter((a) => ["pending", "info_requested", "deferred"].includes(a.status)).length;
  const helps = s.tasks.filter((t) => t.kind === "consultation" && t.cycle === s.experiment.cycle).length;
  const tabs = [
    { id: "overview", label: "Übersicht" },
    { id: "approvals", label: "Freigaben", badge: openApprovals, warn: true },
    { id: "team", label: "Teamarbeit", badge: helps },
    { id: "tasks", label: "Aufgaben", badge: s.blockers.length, warn: true },
    { id: "metrics", label: "Kennzahlen" },
    { id: "costs", label: "Kosten" },
    { id: "files", label: "Dateien" },
  ];
  return (
    <section className="bottom" id="tabs">
      <nav className="tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)} data-testid={`tab-${t.id}`}>
            {t.label}{t.badge ? <span className={`badge ${t.warn ? "warn" : ""}`}>{t.badge}</span> : null}
          </button>))}
      </nav>
      <div className="tab-body">
        {tab === "overview" && <Overview />}
        {tab === "approvals" && <ApprovalCenter />}
        {tab === "team" && <Team />}
        {tab === "tasks" && <TasksBoard />}
        {tab === "metrics" && <Metrics />}
        {tab === "costs" && <Costs />}
        {tab === "files" && <Files />}
      </div>
    </section>
  );
}
