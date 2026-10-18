// Datentypen der Backend-API (siehe src/aicompany/state.py und api/app.py)

export type AgentStatus =
  | "ready" | "working" | "researching" | "communicating" | "waiting_result" | "waiting_approval"
  | "reviewing" | "blocked" | "error" | "done" | "idle" | "paused";

export type TaskStatus = "pending" | "in_progress" | "review" | "blocked" | "completed" | "failed";

export interface TaskBrief {
  id: string; key: string; title: string; agent: string; kind: string; phase: number; status: TaskStatus;
  priority: number; revision_count: number; depends_on: string[]; review_by: string | null; not_before_day: number;
  error: string | null; est_cost_eur: number; actual_cost_eur: number; artifacts: string[]; updated_at: string;
  started_at: string | null; completed_at: string | null; created_by: string;
}

export interface AgentOverview {
  id: string; name: string; title: string; group: string; group_label: string; status: AgentStatus; status_label: string;
  paused: boolean; current_task: TaskBrief | null; next_task: TaskBrief | null; waiting_on: string[];
  progress: { completed: number; total: number } | null; errors: { task_id: string; title: string; error: string | null }[];
  open_approvals: string[]; last_activity: { ts: string; message: string; type: string } | null; model: string;
  cost_eur: number; tokens: { input: number; output: number }; calls: number;
}

export interface EventItem {
  id: number; ts: string; type: string; severity: string; agent: string | null; from_agent: string | null;
  to_agent: string | null; task_id: string | null; run_id: string | null; approval_id: string | null; message: string;
  data: Record<string, unknown>;
}

export interface Approval {
  id: string; task_id: string | null; agent: string; action_type: string; title: string; description: string;
  justification: string; expected_benefit: string; params: Record<string, unknown>; params_hash: string; cost_eur: number;
  recurring_cost_eur: number; budget_impact: { one_time_eur?: number; recurring_eur?: number; total_remaining_before_eur?: number;
    total_remaining_after_eur?: number; fits_budget?: boolean };
  risks: string[]; alternatives: string[]; planned_at: string | null; created_at: string; expires_at: string | null;
  status: string; decided_at: string | null; decided_by: string | null; decision_note: string | null; execution_status: string;
  execution_result: Record<string, unknown> | null; executed_at: string | null;
}

export interface Phase { number: number; name: string; start_day: number; end_day: number; goal: string }

export interface Budget {
  month: string; api_spent_eur: number; api_limit_eur: number; api_remaining_eur: number; external_spent_eur: number;
  external_committed_eur: number; total_spent_eur: number; total_limit_eur: number; total_remaining_eur: number;
  per_run_limit_eur: number; max_calls_per_run: number; api_used_ratio: number; exhausted: boolean; simulated: boolean;
  estimated_share_eur: number;
}

export interface Snapshot {
  mode: string; mode_label: string; simulated: boolean;
  company: { name: string; goal: string; status: string; control: Record<string, boolean> };
  experiment: { started: boolean; start_date: string | null; day: number; days: number; clock: string; plan_phase: Phase | null;
    work_phase: Phase; phases: Phase[]; status: string; final_decision: string | null };
  selected_idea: { id: string; name: string; score: number; rationale: string; selected_at: string } | null;
  ideas: { id: string; name: string; score: number; status: string; data: { lines?: { label: string; points: number; weight: number; rating: number; evidence: string }[] } }[];
  progress: { completed: number; total: number; percent: number | null; formula: string };
  milestones: { id: string; phase: number; title: string; achieved: boolean; achieved_at: string | null; tasks: string[] }[];
  budget: Budget;
  finance_actuals: { revenue_eur: number | null; expenses_eur: number; has_revenue_data: boolean };
  metrics: { id: number; ts: string; name: string; value: number; unit: string; source: string; note: string | null }[];
  risks: { severity: string; description: string; source_task: string; suggested_fix: string }[];
  blockers: { task_id: string; title: string; status: string; error: string | null; agent: string }[];
  next_decision: string | null; ceo_next_step: string | null; next_steps: TaskBrief[];
  decisions: { id: number; ts: string; kind: string; summary: string; rationale: string }[];
  last_report: { path: string; created_at: string } | null;
  active_run: { id: string; started_at: string; agent_calls: number; cost_eur: number } | null;
  last_run: { id: string; status: string; stop_reason: string | null; ended_at: string | null; agent_calls: number; cost_eur: number } | null;
  agents: AgentOverview[]; groups: Record<string, string>; tasks: TaskBrief[]; approvals: Approval[]; last_event_id: number;
  selftest: { passed: boolean; reason: string };
  server?: { run_thread_busy: boolean; last_run_error: string | null };
}

export interface AgentDetail extends AgentOverview {
  mission: string; responsibilities: string[]; rules: string[]; tools: string[]; write_dirs: string[]; task_kinds: string[];
  limits: { max_output_tokens: number; max_input_tokens: number };
  queue: TaskBrief[]; completed_tasks: TaskBrief[]; failed_tasks: TaskBrief[];
  history: (TaskBrief & { history: { ts: string; status: string; note: string; from?: string }[]; feedback: { ts: string; from: string; message: string }[] })[];
  communications: EventItem[]; warnings: EventItem[];
  results: { task_id: string; title: string; artifacts: string[]; completed_at: string | null }[];
  next_step: { type: "planned"; task: TaskBrief } | null; running_action: { type: "running"; task: TaskBrief } | null;
}

export type ConnState = "connecting" | "live" | "reconnecting" | "offline";
