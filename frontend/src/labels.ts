import type { AgentStatus, TaskStatus } from "./types";

export const STATUS: Record<AgentStatus, { label: string; color: string; icon: string; active?: boolean }> = {
  ready: { label: "Bereit", color: "#94a3b8", icon: "●" },
  working: { label: "Arbeitet", color: "#3b82f6", icon: "⚙", active: true },
  researching: { label: "Recherchiert", color: "#06b6d4", icon: "⌕", active: true },
  communicating: { label: "Kommuniziert", color: "#a78bfa", icon: "⇄" },
  waiting_result: { label: "Wartet auf Ergebnis", color: "#64748b", icon: "◷" },
  waiting_approval: { label: "Wartet auf Freigabe", color: "#f59e0b", icon: "⚑" },
  reviewing: { label: "Prüft Ergebnis", color: "#818cf8", icon: "✓", active: true },
  blocked: { label: "Blockiert", color: "#fb923c", icon: "⛔" },
  error: { label: "Fehler aufgetreten", color: "#ef4444", icon: "!" },
  done: { label: "Abgeschlossen", color: "#22c55e", icon: "✔" },
  idle: { label: "Keine Aufgaben", color: "#475569", icon: "○" },
  paused: { label: "Pausiert", color: "#9ca3af", icon: "❚❚" },
};

export const TASK_STATUS: Record<TaskStatus, { label: string; color: string }> = {
  pending: { label: "Wartend", color: "#94a3b8" },
  in_progress: { label: "In Arbeit", color: "#3b82f6" },
  review: { label: "In Prüfung", color: "#818cf8" },
  blocked: { label: "Blockiert", color: "#fb923c" },
  completed: { label: "Abgeschlossen", color: "#22c55e" },
  failed: { label: "Fehlgeschlagen", color: "#ef4444" },
};

export const COMM_KIND: Record<string, { label: string; color: string }> = {
  "comm.assignment": { label: "Aufgabenzuweisung", color: "#60a5fa" },
  "comm.handoff": { label: "Ergebnisübergabe", color: "#2dd4bf" },
  "comm.feedback": { label: "Rückgabe / Feedback", color: "#fbbf24" },
  "comm.message": { label: "Nachricht", color: "#c084fc" },
};

export const COMPANY_STATUS: Record<string, { label: string; color: string }> = {
  running: { label: "Lauf aktiv", color: "#3b82f6" },
  idle: { label: "Bereit – kein Lauf aktiv", color: "#94a3b8" },
  paused: { label: "Pausiert", color: "#f59e0b" },
  draining: { label: "Neue Aufgaben gestoppt", color: "#fb923c" },
  stopped: { label: "Gestoppt", color: "#ef4444" },
  budget_exhausted: { label: "Budget ausgeschöpft", color: "#ef4444" },
  finished: { label: "Experiment abgeschlossen", color: "#22c55e" },
  attention: { label: "Aufmerksamkeit nötig", color: "#fb923c" },
  not_started: { label: "Wartet auf ersten Lauf", color: "#94a3b8" },
};

export const APPROVAL_STATUS: Record<string, string> = {
  pending: "Offen", info_requested: "Rückfrage gestellt", deferred: "Zurückgestellt", approved: "Genehmigt",
  rejected: "Abgelehnt", expired: "Abgelaufen",
};

export const EXECUTION_STATUS: Record<string, { label: string; color: string }> = {
  not_started: { label: "Noch nicht ausgeführt", color: "#94a3b8" },
  running: { label: "Ausführung läuft", color: "#3b82f6" },
  succeeded: { label: "Erfolgreich ausgeführt", color: "#22c55e" },
  failed: { label: "Ausführung fehlgeschlagen", color: "#ef4444" },
  manual_required: { label: "Manuelle Ausführung erforderlich", color: "#f59e0b" },
};

export const ACTION_TYPES: Record<string, string> = {
  publish_website: "Website veröffentlichen", publish_content: "Inhalt veröffentlichen", send_message: "Externe Nachricht",
  paid_ads: "Bezahlte Werbung", purchase: "Kauf", subscription: "Abonnement", contract: "Vertrag", payment: "Zahlung",
  deploy_production: "Produktivsetzung", process_personal_data: "Personenbezogene Daten", request_permission: "Zusätzliche Berechtigung",
};

export const EVENT_CATEGORIES: { id: string; label: string; types: string[] }[] = [
  { id: "tasks", label: "Aufgaben", types: ["task."] },
  { id: "comm", label: "Kommunikation", types: ["comm."] },
  { id: "work", label: "Arbeit & Dateien", types: ["agent.", "file.", "code.", "analysis.", "report."] },
  { id: "decisions", label: "Entscheidungen & Meilensteine", types: ["ceo.", "milestone.", "phase.", "goal."] },
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
