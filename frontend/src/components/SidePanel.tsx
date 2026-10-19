import { useEffect, useState } from "react";
import { agentName, useApp, type Panel } from "../context";
import { clock, COMM_KIND, eur, STATUS, TASK_STATUS } from "../labels";
import type { AgentDetail, Approval, EventItem, TaskBrief } from "../types";

function useFetch<T>(path: string | null, deps: unknown[] = []): { data: T | null; error: string | null } {
  const { api } = useApp();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    api.get<T>(path).then((d) => alive && (setData(d), setError(null))).catch((e) => alive && setError(String(e.message)));
    return () => { alive = false; };
  }, [path, ...deps]);
  return { data, error };
}

function TaskRow({ t }: { t: TaskBrief }) {
  const { open } = useApp();
  const st = TASK_STATUS[t.status];
  return (
    <li className="task-row" onClick={() => open({ kind: "task", id: t.id })}>
      <span className="pill" style={{ borderColor: st.color, color: st.color }}>{st.label}</span>
      <span className="grow">{t.title}{t.revision_count ? <span className="muted"> · Überarbeitung {t.revision_count}</span> : null}</span>
      <span className="muted small">{eur(t.actual_cost_eur, 4)}</span>
    </li>
  );
}

function AgentPanel({ id }: { id: string }) {
  const { state, api, toast, refresh, open } = useApp();
  const { data, error } = useFetch<AgentDetail>(`/api/agents/${id}`, [state.lastEventId, state.snapshotAt]);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Lade …</p>;
  const st = STATUS[data.status];
  async function togglePause() {
    try {
      await api.post(`/api/agents/${id}/${data!.paused ? "resume" : "pause"}`);
      toast(data!.paused ? `${data!.name} wieder aktiviert` : `${data!.name} pausiert`);
      await refresh();
    } catch (e) { toast(String((e as Error).message), "error"); }
  }
  return (
    <div className="agent-panel" data-testid="agent-panel">
      <div className="panel-title">
        <span className="avatar big" style={{ borderColor: st.color }}>{data.name.slice(0, 2)}</span>
        <div><h2>{data.name}</h2><div className="muted">{data.title} · {data.group_label}</div></div>
      </div>
      <div className="status-line"><span className="dot" style={{ background: st.color }} />{st.label}</div>
      <button className="btn" onClick={togglePause}>{data.paused ? "▶ Agent aktivieren" : "❚❚ Agent pausieren"}</button>
      <section><h3>Mission</h3><p>{data.mission}</p>
        <ul className="bullets">{data.responsibilities.map((r) => <li key={r}>{r}</li>)}</ul></section>
      <section><h3>Aktuell</h3>
        {data.running_action ? <p><span className="tag run">läuft</span> {data.running_action.task.title}</p> : <p className="muted">Keine laufende Aktion.</p>}
        {data.next_step ? <p><span className="tag plan">geplant</span> {data.next_step.task.title}
          {data.waiting_on.length > 0 && <span className="muted"> – wartet auf: {data.waiting_on.join(", ")}</span>}</p>
          : <p className="muted">Kein nächster Schritt aus dem Aufgabenstatus ableitbar.</p>}
      </section>
      <section><h3>Warteschlange ({data.queue.length})</h3><ul className="task-list">{data.queue.map((t) => <TaskRow key={t.id} t={t} />)}</ul></section>
      <section><h3>Abgeschlossen ({data.completed_tasks.length})</h3><ul className="task-list">{data.completed_tasks.map((t) => <TaskRow key={t.id} t={t} />)}</ul></section>
      {data.failed_tasks.length > 0 && <section><h3>Fehlgeschlagen / blockiert</h3><ul className="task-list">{data.failed_tasks.map((t) => <TaskRow key={t.id} t={t} />)}</ul></section>}
      <section><h3>Ergebnisse & Dateien</h3>
        {data.results.length === 0 ? <p className="muted">Noch keine Ergebnisse.</p> :
          <ul className="file-list">{data.results.flatMap((r) => r.artifacts.map((p) => <li key={p}><button className="link" onClick={() => open({ kind: "file", path: p })}>{p}</button></li>))}</ul>}
      </section>
      <section><h3>Werkzeuge & Berechtigungen</h3>
        <div className="chips">{data.tools.map((t) => <span key={t} className="chip">{t}</span>)}</div>
        <p className="small muted">Schreibrechte: {data.write_dirs.map((d) => d + "/").join(", ")} · Aufgabenarten: {data.task_kinds.join(", ")}</p>
      </section>
      <section><h3>Modell & Kosten</h3>
        <table className="kv"><tbody>
          <tr><td>Modell</td><td>{data.model}</td></tr>
          <tr><td>Aufrufe</td><td>{data.calls}</td></tr>
          <tr><td>Tokens (ein/aus)</td><td>{data.tokens.input?.toLocaleString("de-DE") ?? 0} / {data.tokens.output?.toLocaleString("de-DE") ?? 0}</td></tr>
          <tr><td>Kosten</td><td>{eur(data.cost_eur, 4)}{state.snapshot?.simulated ? " (simuliert)" : ""}</td></tr>
          <tr><td>Tokenlimits</td><td>Eingabe {data.limits.max_input_tokens} / Ausgabe {data.limits.max_output_tokens}</td></tr>
        </tbody></table>
      </section>
      <section><h3>Letzte Kommunikation</h3>
        {data.communications.length === 0 ? <p className="muted">Noch keine.</p> :
          <ul className="comm-list">{data.communications.map((e) => (
            <li key={e.id} onClick={() => open({ kind: "event", id: e.id })}>
              <span className="dot" style={{ background: COMM_KIND[e.type]?.color }} />
              <span className="small muted">{clock(e.ts)}</span> {agentName(state, e.from_agent)} → {agentName(state, e.to_agent)}: {e.message}
            </li>))}</ul>}
      </section>
      <section><h3>Fehler & Warnungen</h3>
        {data.warnings.length === 0 ? <p className="muted">Keine.</p> :
          <ul className="comm-list">{data.warnings.map((e) => <li key={e.id} className={`sev-${e.severity}`}>{clock(e.ts)} {e.message}</li>)}</ul>}
      </section>
      <section><h3>Verlauf</h3>
        {data.history.map((t) => (
          <details key={t.id}><summary>{t.title} <span className="muted small">({TASK_STATUS[t.status].label})</span></summary>
            <ol className="history">{t.history.map((h, i) => <li key={i}><span className="small muted">{clock(h.ts)}</span> {h.from ? `${h.from} → ` : ""}{h.status}: {h.note}</li>)}</ol>
            {t.feedback.length > 0 && <><b className="small">Feedback</b><ul className="bullets">{t.feedback.map((f, i) => <li key={i}><b>{f.from}:</b> {f.message}</li>)}</ul></>}
          </details>))}
      </section>
    </div>
  );
}

function EdgePanel({ a, b }: { a: string; b: string }) {
  const { state, open } = useApp();
  const { data, error } = useFetch<{ event: EventItem; task: TaskBrief | null }[]>(`/api/communications?a=${a}&b=${b}`, [state.lastEventId]);
  return (
    <div data-testid="edge-panel">
      <h2>{agentName(state, a)} ⇄ {agentName(state, b)}</h2>
      <p className="muted small">Nur tatsächlich protokollierte Kommunikation, Aufgabenübergaben und Rückgaben – keine bloßen Abhängigkeiten.</p>
      {error && <p className="error">{error}</p>}
      {!data ? <p className="muted">Lade …</p> : data.length === 0 ? <p className="muted">Keine Kommunikation.</p> : (
        <ul className="comm-detail">
          {data.map(({ event: e, task }) => (
            <li key={e.id}>
              <div className="comm-head">
                <span className="pill" style={{ borderColor: COMM_KIND[e.type]?.color, color: COMM_KIND[e.type]?.color }}>{COMM_KIND[e.type]?.label}</span>
                <span className="small muted">{new Date(e.ts).toLocaleString("de-DE")}</span>
              </div>
              <table className="kv"><tbody>
                <tr><td>Absender</td><td>{agentName(state, e.from_agent)}</td></tr>
                <tr><td>Empfänger</td><td>{agentName(state, e.to_agent)}</td></tr>
                <tr><td>Anlass</td><td>{e.message}</td></tr>
                {task && <tr><td>Aufgabe</td><td><button className="link" onClick={() => open({ kind: "task", id: task.id })}>{task.title}</button> ({TASK_STATUS[task.status].label})</td></tr>}
                {Array.isArray(e.data.artifacts) && (e.data.artifacts as string[]).length > 0 && <tr><td>Dateien</td><td>{(e.data.artifacts as string[]).map((p) =>
                  <button key={p} className="link block" onClick={() => open({ kind: "file", path: p })}>{p}</button>)}</td></tr>}
                {Array.isArray(e.data.reasons) && <tr><td>Gründe</td><td>{(e.data.reasons as string[]).join(" · ")}</td></tr>}
                <tr><td>Status der Übergabe</td><td>{task ? TASK_STATUS[task.status].label : "protokolliert"}</td></tr>
              </tbody></table>
            </li>))}
        </ul>
      )}
    </div>
  );
}

function EventPanel({ id }: { id: number }) {
  const { state, open } = useApp();
  const { data, error } = useFetch<{ event: EventItem; task: TaskBrief | null; approval: Approval | null }>(`/api/events/${id}`);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Lade …</p>;
  const e = data.event;
  const files = (Array.isArray(e.data.files) ? e.data.files : Array.isArray(e.data.artifacts) ? e.data.artifacts : e.data.path ? [e.data.path] : []) as string[];
  return (
    <div data-testid="event-panel">
      <h2>Ereignis #{e.id}</h2>
      <table className="kv"><tbody>
        <tr><td>Zeit</td><td>{new Date(e.ts).toLocaleString("de-DE")}</td></tr>
        <tr><td>Art</td><td>{e.type}</td></tr>
        <tr><td>Schweregrad</td><td>{e.severity}</td></tr>
        <tr><td>Agent</td><td>{e.from_agent && e.to_agent ? `${agentName(state, e.from_agent)} → ${agentName(state, e.to_agent)}` : agentName(state, e.agent)}</td></tr>
        <tr><td>Beschreibung</td><td>{e.message}</td></tr>
        {e.run_id && <tr><td>Lauf</td><td>{e.run_id}</td></tr>}
        {data.task && <tr><td>Aufgabe</td><td><button className="link" onClick={() => open({ kind: "task", id: data.task!.id })}>{data.task.title}</button></td></tr>}
        {data.approval && <tr><td>Freigabe</td><td>{data.approval.id}: {data.approval.title} ({data.approval.status})</td></tr>}
      </tbody></table>
      {files.length > 0 && <><h3>Dateien</h3><ul className="file-list">{files.map((p) => <li key={p}><button className="link" onClick={() => open({ kind: "file", path: p })}>{p}</button></li>)}</ul></>}
      <h3>Daten</h3>
      <pre className="code">{JSON.stringify(e.data, null, 2)}</pre>
    </div>
  );
}

function TaskPanel({ id }: { id: string }) {
  const { state, open, api, toast, refresh } = useApp();
  const { data, error } = useFetch<TaskBrief & { goal: string; description: string; acceptance: string[]; result: { output: unknown; derived: unknown; simulated: boolean } | null;
    history: { ts: string; status: string; note: string; from?: string }[]; feedback: { from: string; message: string }[] }>(`/api/tasks/${id}`, [state.lastEventId]);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Lade …</p>;
  const st = TASK_STATUS[data.status];
  async function retry() {
    try { await api.post(`/api/tasks/${id}/retry`); toast("Aufgabe wird erneut versucht"); await refresh(); }
    catch (e) { toast(String((e as Error).message), "error"); }
  }
  return (
    <div data-testid="task-panel">
      <h2>{data.title}</h2>
      <p><span className="pill" style={{ borderColor: st.color, color: st.color }}>{st.label}</span> <span className="muted">{data.id} · {data.key} · {agentName(state, data.agent)}</span></p>
      {(data.status === "failed" || data.status === "blocked") && <button className="btn" onClick={retry}>⟲ Erneut versuchen</button>}
      <table className="kv"><tbody>
        <tr><td>Ziel</td><td>{data.goal}</td></tr>
        <tr><td>Beschreibung</td><td>{data.description}</td></tr>
        <tr><td>Abhängigkeiten</td><td>{data.depends_on.join(", ") || "–"}</td></tr>
        <tr><td>Ausgabeformat</td><td>{data.kind}</td></tr>
        <tr><td>Priorität</td><td>{data.priority}</td></tr>
        <tr><td>Kosten (geschätzt/tatsächlich)</td><td>{eur(data.est_cost_eur, 4)} / {eur(data.actual_cost_eur, 4)}</td></tr>
        <tr><td>Überarbeitungen</td><td>{data.revision_count}</td></tr>
        {data.error && <tr><td>Fehler</td><td className="error">{data.error}</td></tr>}
      </tbody></table>
      <h3>Akzeptanzkriterien</h3><ul className="bullets">{data.acceptance.map((a) => <li key={a}>{a}</li>)}</ul>
      {data.artifacts.length > 0 && <><h3>Dateien</h3><ul className="file-list">{data.artifacts.map((p) => <li key={p}><button className="link" onClick={() => open({ kind: "file", path: p })}>{p}</button></li>)}</ul></>}
      {data.feedback.length > 0 && <><h3>Feedback</h3><ul className="bullets">{data.feedback.map((f, i) => <li key={i}><b>{f.from}:</b> {f.message}</li>)}</ul></>}
      <h3>Verlauf</h3>
      <ol className="history">{data.history.map((h, i) => <li key={i}><span className="small muted">{clock(h.ts)}</span> {h.from ? `${h.from} → ` : ""}{h.status}: {h.note}</li>)}</ol>
      {data.result && <><h3>Ergebnis {data.result.simulated ? "(simuliert)" : ""}</h3><pre className="code">{JSON.stringify(data.result.output, null, 2)}</pre>
        {data.result.derived && Object.keys(data.result.derived as object).length > 0 && <><h3>Vom Programm berechnet</h3><pre className="code">{JSON.stringify(data.result.derived, null, 2)}</pre></>}</>}
    </div>
  );
}

function FilePanel({ path }: { path: string }) {
  const { data, error } = useFetch<string>(`/api/files/content?path=${encodeURIComponent(path)}`);
  return (
    <div data-testid="file-panel">
      <h2>{path}</h2>
      <p className="muted small">Wird als reiner Text angezeigt – Inhalte werden nie ausgeführt.</p>
      {error ? <p className="error">{error}</p> : data === null ? <p className="muted">Lade …</p> : <pre className="code file">{data}</pre>}
    </div>
  );
}

export function SidePanel({ panel, onClose }: { panel: Panel; onClose: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="overlay" onClick={onClose}>
      <aside className="side-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <button className="close" onClick={onClose} aria-label="Schließen">✕</button>
        {panel.kind === "agent" && <AgentPanel id={panel.id} />}
        {panel.kind === "edge" && <EdgePanel a={panel.a} b={panel.b} />}
        {panel.kind === "event" && <EventPanel id={panel.id} />}
        {panel.kind === "file" && <FilePanel path={panel.path} />}
        {panel.kind === "task" && <TaskPanel id={panel.id} />}
      </aside>
    </div>
  );
}
