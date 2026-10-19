import type { AgentStatus, TaskStatus } from "./types";

// Statusfarben: neutral bis auf semantische Zustände (aktiv = Akzent, Warten = Bernstein, Fehler = Rot, fertig = Grün)
const C = { accent: "var(--accent)", muted: "var(--muted)", warn: "var(--warn)", err: "var(--err)", ok: "var(--ok)", text: "var(--text-2)" };

export const STATUS: Record<AgentStatus, { label: string; color: string; icon: string; active?: boolean }> = {
  ready: { label: "Bereit", color: C.text, icon: "" },
  working: { label: "Arbeitet", color: C.accent, icon: "", active: true },
  researching: { label: "Recherchiert", color: C.accent, icon: "", active: true },
  communicating: { label: "Im Austausch", color: C.accent, icon: "" },
  waiting_result: { label: "Wartet auf Zuarbeit", color: C.muted, icon: "" },
  waiting_approval: { label: "Wartet auf Freigabe", color: C.warn, icon: "" },
  reviewing: { label: "Prüft Ergebnis", color: C.accent, icon: "", active: true },
  blocked: { label: "Blockiert", color: C.warn, icon: "" },
  error: { label: "Fehler", color: C.err, icon: "" },
  done: { label: "Erledigt", color: C.ok, icon: "" },
  idle: { label: "Keine Aufgaben", color: C.muted, icon: "" },
  paused: { label: "Pausiert", color: C.muted, icon: "" },
};

export const TASK_STATUS: Record<TaskStatus, { label: string; color: string }> = {
  pending: { label: "Wartend", color: C.muted },
  in_progress: { label: "In Arbeit", color: C.accent },
  review: { label: "In Prüfung", color: C.accent },
  blocked: { label: "Blockiert", color: C.warn },
  completed: { label: "Erledigt", color: C.ok },
  failed: { label: "Fehlgeschlagen", color: C.err },
};

export const COMM_KIND: Record<string, { label: string; color: string; dashed?: boolean }> = {
  "comm.assignment": { label: "Auftrag", color: C.text },
  "comm.handoff": { label: "Übergabe", color: C.accent },
  "comm.feedback": { label: "Rückgabe", color: C.warn },
  "comm.message": { label: "Nachricht", color: C.muted, dashed: true },
  "comm.help_request": { label: "Bittet um Hilfe", color: "var(--team)" },
  "comm.help_answer": { label: "Hilft", color: "var(--team)" },
  "comm.help_offer": { label: "Bietet Hilfe an", color: "var(--team)", dashed: true },
};

export const COMPANY_STATUS: Record<string, { label: string; color: string }> = {
  running: { label: "Arbeitet", color: C.accent },
  idle: { label: "Bereit", color: C.ok },
  paused: { label: "Pausiert", color: C.warn },
  draining: { label: "Neue Aufgaben gestoppt", color: C.warn },
  stopped: { label: "Gestoppt", color: C.err },
  budget_exhausted: { label: "Budget ausgeschöpft", color: C.err },
  finished: { label: "Angehalten (Zyklengrenze)", color: C.muted },
  attention: { label: "Braucht Aufmerksamkeit", color: C.warn },
  not_started: { label: "Wartet auf ersten Lauf", color: C.muted },
};

export const APPROVAL_STATUS: Record<string, string> = {
  pending: "Offen", info_requested: "Rückfrage gestellt", deferred: "Zurückgestellt", approved: "Genehmigt",
  rejected: "Abgelehnt", expired: "Abgelaufen",
};

export const EXECUTION_STATUS: Record<string, { label: string; color: string }> = {
  not_started: { label: "Noch nicht ausgeführt", color: C.muted },
  running: { label: "Ausführung läuft", color: C.accent },
  succeeded: { label: "Erfolgreich ausgeführt", color: C.ok },
  failed: { label: "Ausführung fehlgeschlagen", color: C.err },
  manual_required: { label: "Manuelle Ausführung erforderlich", color: C.warn },
};

export const ACTION_TYPES: Record<string, string> = {
  publish_website: "Website veröffentlichen", publish_content: "Inhalt veröffentlichen", send_message: "Externe Nachricht",
  paid_ads: "Bezahlte Werbung", purchase: "Kauf", subscription: "Abonnement", contract: "Vertrag", payment: "Zahlung",
  deploy_production: "Produktivsetzung", process_personal_data: "Personenbezogene Daten", request_permission: "Zusätzliche Berechtigung",
};

export const EVENT_CATEGORIES: { id: string; label: string; types: string[] }[] = [
  { id: "tasks", label: "Aufgaben", types: ["task."] },
  { id: "team", label: "Teamarbeit", types: ["comm.help_", "task.waiting_help", "collab."] },
  { id: "comm", label: "Aufträge & Übergaben", types: ["comm."] },
  { id: "work", label: "Arbeit & Dateien", types: ["agent.", "file.", "code.", "analysis.", "report."] },
  { id: "decisions", label: "Entscheidungen & Meilensteine", types: ["ceo.", "milestone.", "phase.", "goal.", "cycle."] },
  { id: "approvals", label: "Freigaben", types: ["approval."] },
  { id: "budget", label: "Budget", types: ["budget."] },
  { id: "system", label: "System, Fehler & Sicherheit", types: ["run.", "api.", "control.", "security.", "qa.", "metric."] },
];

export function eventCategory(type: string, data?: Record<string, unknown>): string {
  if (data && data.kind === "budget.warning") return "budget";
  return EVENT_CATEGORIES.find((c) => c.types.some((p) => type.startsWith(p)))?.id ?? "system";
}

export const SEVERITY_ORDER = ["debug", "info", "success", "warning", "error", "critical"];

export function eur(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "–";
  return v.toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: Math.max(digits, 4) }) + " €";
}

export function relTime(ts: string | null | undefined, now = Date.now()): string {
  if (!ts) return "–";
  const s = Math.max(0, Math.round((now - Date.parse(ts)) / 1000));
  if (s < 60) return `vor ${s} s`;
  if (s < 3600) return `vor ${Math.round(s / 60)} min`;
  if (s < 86400) return `vor ${Math.round(s / 3600)} h`;
  return new Date(ts).toLocaleDateString("de-DE");
}

export function clock(ts: string): string {
  return new Date(ts).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
