import { useState } from "react";
import { agentName, useApp } from "../context";
import { ACTION_TYPES, APPROVAL_STATUS, eur, EXECUTION_STATUS } from "../labels";
import type { Approval } from "../types";

function ApprovalCard({ ap }: { ap: Approval }) {
  const { api, state, toast, refresh, open } = useApp();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [manualCost, setManualCost] = useState(String(ap.cost_eur + ap.recurring_cost_eur));
  const isOpen = ["pending", "info_requested", "deferred"].includes(ap.status);
  const exec = EXECUTION_STATUS[ap.execution_status];

  async function decide(decision: "approve" | "reject" | "request_info" | "defer") {
    if (decision === "request_info" && !note.trim()) { toast("Bitte die Rückfrage im Notizfeld formulieren", "error"); return; }
    setBusy(true);
    try {
      const res = await api.post<Approval>(`/api/approvals/${ap.id}/decision`, {
        decision, note, params_hash: decision === "approve" ? ap.params_hash : undefined,
      });
      const execLabel = EXECUTION_STATUS[res.execution_status]?.label;
      toast(`${ap.id}: ${APPROVAL_STATUS[res.status]}${res.status === "approved" ? ` – ${execLabel}` : ""}`);
      setConfirming(false);
      await refresh();
    } catch (e) {
      toast(`Abgewiesen: ${(e as Error).message}`, "error");
    } finally { setBusy(false); }
  }

  async function confirmManual(executed: boolean) {
    setBusy(true);
    try {
      await api.post(`/api/approvals/${ap.id}/confirm-manual`, { executed, actual_cost_eur: executed ? Number(manualCost) || 0 : 0, note });
      toast(executed ? "Manuelle Ausführung bestätigt" : "Als nicht ausgeführt markiert");
      await refresh();
    } catch (e) { toast(`Abgewiesen: ${(e as Error).message}`, "error"); }
    finally { setBusy(false); }
  }

  const bi = ap.budget_impact;
  return (
    <article className={`approval ${isOpen ? "open" : ""}`} data-testid={`approval-${ap.id}`}>
      <header>
        <div>
          <span className="pill">{ACTION_TYPES[ap.action_type] ?? ap.action_type}</span>
          <h3>{ap.title}</h3>
          <div className="muted small">{ap.id} · beantragt von {agentName(state, ap.agent)} · {new Date(ap.created_at).toLocaleString("de-DE")}
            {ap.expires_at && ` · läuft ab ${new Date(ap.expires_at).toLocaleString("de-DE")}`}</div>
        </div>
        <div className="approval-status">
          <b data-testid="approval-status">{APPROVAL_STATUS[ap.status] ?? ap.status}</b>
          {ap.status === "approved" && <span style={{ color: exec.color }} data-testid="execution-status">{exec.label}</span>}
        </div>
      </header>
      <div className="approval-grid">
        <div><div className="label">Geplante Aktion</div><p>{ap.description}</p></div>
        <div><div className="label">Begründung</div><p>{ap.justification}</p></div>
        <div><div className="label">Erwarteter Nutzen</div><p>{ap.expected_benefit}</p></div>
        <div><div className="label">Kosten</div>
          <p><b>{eur(ap.cost_eur)}</b> einmalig{ap.recurring_cost_eur ? ` + ${eur(ap.recurring_cost_eur)} wiederkehrend` : ""}</p>
          <p className="small">Restbudget {eur(bi.total_remaining_before_eur)} → {eur(bi.total_remaining_after_eur)}
            {bi.fits_budget === false && <b className="error"> – übersteigt das Budget</b>}</p></div>
        <div><div className="label">Risiken & Unsicherheiten</div><ul className="bullets">{ap.risks.map((r) => <li key={r}>{r}</li>)}</ul></div>
        <div><div className="label">Alternativen</div><ul className="bullets">{ap.alternatives.map((r) => <li key={r}>{r}</li>)}{!ap.alternatives.length && <li className="muted">keine</li>}</ul></div>
        <div><div className="label">Ausführungszeit</div><p>{ap.planned_at ? new Date(ap.planned_at).toLocaleString("de-DE") : "sofort nach Genehmigung"}</p></div>
        <div><div className="label">Zugehörige Aufgabe</div><p>{ap.task_id ? <button className="link" onClick={() => open({ kind: "task", id: ap.task_id! })}>{ap.task_id}</button> : "–"}</p></div>
      </div>
      <details>
        <summary>Exakte Parameter (werden bei Genehmigung unverändert ausgeführt)</summary>
        <pre className="code">{JSON.stringify(ap.params, null, 2)}</pre>
        <div className="small muted">Parameter-Hash: <code>{ap.params_hash.slice(0, 16)}…</code></div>
      </details>
      {ap.decision_note && <p className="small"><b>Notiz:</b> {ap.decision_note} ({ap.decided_by})</p>}
      {ap.execution_result && <p className="small exec-result"><b>Ergebnis:</b> {String(ap.execution_result.message ?? "")}</p>}
      {isOpen && (
        <div className="approval-actions">
          <input placeholder="Notiz / Rückfrage (optional)" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Notiz" />
          {!confirming ? (
            <button className="btn primary" disabled={busy} onClick={() => setConfirming(true)} data-testid="btn-approve">Genehmigen …</button>
          ) : (
            <span className="confirm">
              Genau diese Aktion für {eur(ap.cost_eur + ap.recurring_cost_eur)} genehmigen?
              <button className="btn primary" disabled={busy} onClick={() => decide("approve")} data-testid="btn-approve-confirm">Ja, genehmigen</button>
              <button className="btn ghost" disabled={busy} onClick={() => setConfirming(false)}>Abbrechen</button>
            </span>
          )}
          <button className="btn danger" disabled={busy} onClick={() => decide("reject")} data-testid="btn-reject">Ablehnen</button>
          <button className="btn" disabled={busy} onClick={() => decide("request_info")}>Weitere Informationen</button>
          <button className="btn ghost" disabled={busy || ap.status === "deferred"} onClick={() => decide("defer")}>Zurückstellen</button>
        </div>
      )}
      {ap.execution_status === "manual_required" && (
        <div className="approval-actions">
          <span className="small">Selbst ausgeführt? Tatsächliche Kosten (€):</span>
          <input type="number" min="0" step="0.01" value={manualCost} onChange={(e) => setManualCost(e.target.value)} aria-label="Tatsächliche Kosten" />
          <button className="btn primary" disabled={busy} onClick={() => confirmManual(true)}>Ausführung bestätigen</button>
          <button className="btn" disabled={busy} onClick={() => confirmManual(false)}>Nicht ausgeführt</button>
        </div>
      )}
    </article>
  );
}

export function ApprovalCenter() {
  const { state } = useApp();
  const all = state.snapshot!.approvals;
  const open = all.filter((a) => ["pending", "info_requested", "deferred"].includes(a.status));
  const decided = all.filter((a) => !open.includes(a));
  return (
    <div className="approvals" data-testid="approval-center">
      <p className="muted small">Agenten planen autonom; externe Aktionen werden hier beantragt. Das Backend prüft jede Entscheidung
        (Berechtigung, Budget, unveränderte Parameter) und führt nur genau die genehmigte Aktion aus – höchstens einmal.</p>
      <h3>Offene Anträge ({open.length})</h3>
      {open.length === 0 && <p className="muted">Keine offenen Freigaben.</p>}
      {open.map((a) => <ApprovalCard key={a.id} ap={a} />)}
      {decided.length > 0 && <><h3>Entschiedene Anträge</h3>{decided.map((a) => <ApprovalCard key={a.id} ap={a} />)}</>}
    </div>
  );
}
