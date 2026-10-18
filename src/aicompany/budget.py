"""Kostenkontrolle: Schätzung vor jedem Aufruf, Erfassung danach, Warnschwellen und harter Stopp.

Hinweis: Ein anwendungseigenes Limit ist keine absolute Garantie gegen Abrechnungen des
API-Anbieters (z. B. bei parallelen Prozessen außerhalb dieses Systems). Setze zusätzlich
ein Ausgabenlimit im Konto des Anbieters.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import ModelPrice, Settings
from .db import Database, month_key, now_iso
from .events import EventBus


class BudgetExceeded(Exception):
    def __init__(self, reason: str, scope: str):
        super().__init__(reason)
        self.reason = reason
        self.scope = scope


@dataclass
class RunBudget:
    """Laufbezogene Zähler (ein Lauf = ein Prozess, daher in-memory plus Persistenz im runs-Datensatz)."""

    run_id: str
    calls_used: int = 0
    cost_eur: float = 0.0
    reserved_eur: float = 0.0
    reserved_calls: int = 0
    web_search_calls: int = 0
    reservations: dict[str, tuple[float, int]] = field(default_factory=dict)


@dataclass
class CallUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 1
    web_search_calls: int = 0
    known: bool = True  # False = Verbrauchsdaten fehlen, es wird konservativ geschätzt


class BudgetGuard:
    def __init__(self, db: Database, settings: Settings, events: EventBus):
        self.db = db
        self.settings = settings
        self.cfg = settings.budget
        self.events = events

    # ---------- Preise & Schätzungen ----------
    def price(self, model: str) -> tuple[ModelPrice, bool]:
        """Liefert (Preis, bekannt). Unbekannte Modelle werden mit dem teuersten Tarif × Aufschlag bewertet."""
        if model in self.settings.pricing:
            return self.settings.pricing[model], True
        prices = list(self.settings.pricing.values()) or [ModelPrice(input_per_mtok_usd=5, output_per_mtok_usd=30)]
        worst_in = max(p.input_per_mtok_usd for p in prices) * self.cfg.uncertainty_markup
        worst_out = max(p.output_per_mtok_usd for p in prices) * self.cfg.uncertainty_markup
        return ModelPrice(input_per_mtok_usd=worst_in, output_per_mtok_usd=worst_out), False

    def cost_eur(self, model: str, input_tokens: int, output_tokens: int, web_search_calls: int = 0) -> float:
        price, _ = self.price(model)
        usd = input_tokens / 1e6 * price.input_per_mtok_usd + output_tokens / 1e6 * price.output_per_mtok_usd
        usd += web_search_calls * self.settings.web_search.cost_per_call_usd
        return round(usd * self.cfg.usd_to_eur, 6)

    def estimate_call(self, model: str, prompt_chars: int, max_output_tokens: int, web_search_calls: int = 0) -> float:
        # Konservativ: ~3 Zeichen pro Token, volle Ausgabelänge, Aufschlag für Unsicherheit
        input_tokens = int(prompt_chars / 3) + 500
        return round(self.cost_eur(model, input_tokens, max_output_tokens, web_search_calls) * self.cfg.uncertainty_markup, 6)

    # ---------- Summen ----------
    def month_spend(self, kinds: tuple[str, ...] = ("api",), month: str | None = None) -> float:
        marks = ",".join("?" * len(kinds))
        row = self.db.query_one(
            f"SELECT COALESCE(SUM(cost_eur),0) AS s FROM cost_records WHERE month = ? AND kind IN ({marks})",
            (month or month_key(), *kinds),
        )
        return float(row["s"])

    def committed_external(self) -> float:
        """Genehmigte, aber noch nicht abgerechnete externe Ausgaben (reservieren Gesamtbudget)."""
        row = self.db.query_one(
            "SELECT COALESCE(SUM(cost_eur + recurring_cost_eur),0) AS s FROM approvals WHERE status='approved'"
            " AND execution_status IN ('not_started','running','manual_required') AND substr(decided_at,1,7)=?",
            (month_key(),),
        )
        return float(row["s"])

    def summary(self) -> dict:
        api = self.month_spend(("api", "tool"))
        external = self.month_spend(("external",))
        committed = self.committed_external()
        total = api + external
        return {
            "month": month_key(),
            "api_spent_eur": round(api, 4),
            "api_limit_eur": self.cfg.monthly_api_eur,
            "api_remaining_eur": round(max(0.0, self.cfg.monthly_api_eur - api), 4),
            "external_spent_eur": round(external, 4),
            "external_committed_eur": round(committed, 4),
            "total_spent_eur": round(total, 4),
            "total_limit_eur": self.cfg.monthly_total_eur,
            "total_remaining_eur": round(max(0.0, self.cfg.monthly_total_eur - total - committed), 4),
            "per_run_limit_eur": self.cfg.per_run_eur,
            "max_calls_per_run": self.cfg.max_agent_calls_per_run,
            "api_used_ratio": round(api / self.cfg.monthly_api_eur, 4),
            "exhausted": api >= self.cfg.monthly_api_eur or total >= self.cfg.monthly_total_eur,
            "simulated": self.settings.mode == "dry_run",
            "estimated_share_eur": round(self._estimated_share(), 4),
        }

    def _estimated_share(self) -> float:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(cost_eur),0) AS s FROM cost_records WHERE month=? AND estimated=1", (month_key(),)
        )
        return float(row["s"])

    def by_agent(self) -> list[dict]:
        rows = self.db.query(
            "SELECT agent, model, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,"
            " SUM(cost_eur) AS cost_eur, SUM(estimated) AS estimated_calls FROM cost_records WHERE kind IN ('api','tool')"
            " GROUP BY agent, model ORDER BY cost_eur DESC"
        )
        return [dict(r) for r in rows]

    # ---------- Prüfungen ----------
    def check_before_call(self, run: RunBudget, estimate_eur: float) -> None:
        """Vor jedem Aufruf: Aufruflimit, Laufbudget, Monats-API-Budget und Gesamtbudget."""
        if run.calls_used + run.reserved_calls >= self.cfg.max_agent_calls_per_run:
            raise BudgetExceeded(
                f"Limit von {self.cfg.max_agent_calls_per_run} Agentenaufrufen pro Lauf erreicht", "calls"
            )
        if run.cost_eur + run.reserved_eur + estimate_eur > self.cfg.per_run_eur:
            raise BudgetExceeded(
                f"Laufbudget {self.cfg.per_run_eur:.2f} € würde überschritten "
                f"(bisher {run.cost_eur:.4f} €, geschätzt +{estimate_eur:.4f} €)", "run"
            )
        api = self.month_spend(("api", "tool")) + run.reserved_eur
        if api + estimate_eur > self.cfg.monthly_api_eur:
            raise BudgetExceeded(f"Monatliches API-Budget {self.cfg.monthly_api_eur:.2f} € erreicht", "api_month")
        total = self.month_spend(("api", "tool", "external")) + self.committed_external() + run.reserved_eur
        if total + estimate_eur > self.cfg.monthly_total_eur:
            raise BudgetExceeded(f"Monatliches Gesamtbudget {self.cfg.monthly_total_eur:.2f} € erreicht", "total_month")

    def reserve(self, run: RunBudget, key: str, estimate_eur: float) -> None:
        self.check_before_call(run, estimate_eur)
        run.reserved_eur += estimate_eur
        run.reserved_calls += 1
        run.reservations[key] = (estimate_eur, 1)

    def release(self, run: RunBudget, key: str) -> None:
        est, calls = run.reservations.pop(key, (0.0, 0))
        run.reserved_eur = max(0.0, run.reserved_eur - est)
        run.reserved_calls = max(0, run.reserved_calls - calls)

    def record_call(
        self,
        run: RunBudget,
        *,
        key: str,
        task_id: str | None,
        agent: str,
        model: str,
        usage: CallUsage | None,
        estimate_eur: float,
        note: str = "",
    ) -> float:
        """Nach jedem Aufruf: tatsächliche (oder konservativ geschätzte) Kosten verbuchen."""
        self.release(run, key)
        estimated = usage is None or not usage.known
        if estimated:
            cost = estimate_eur
            in_tok = out_tok = tool_calls = 0
        else:
            cost = self.cost_eur(model, usage.input_tokens, usage.output_tokens, usage.web_search_calls)
            _, known_price = self.price(model)
            estimated = not known_price
            in_tok, out_tok, tool_calls = usage.input_tokens, usage.output_tokens, usage.web_search_calls
        run.calls_used += 1
        run.cost_eur += cost
        run.web_search_calls += tool_calls
        self.db.execute(
            "INSERT INTO cost_records(ts, month, run_id, task_id, agent, model, kind, input_tokens, output_tokens, tool_calls,"
            " cost_eur, estimated, simulated, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now_iso(), month_key(), run.run_id, task_id, agent, model, "api", in_tok, out_tok, tool_calls, cost,
             int(estimated), int(self.settings.mode == "dry_run"), note),
        )
        if task_id:
            self.db.execute("UPDATE tasks SET actual_cost_eur = actual_cost_eur + ? WHERE id = ?", (cost, task_id))
        self.db.execute("UPDATE runs SET agent_calls=?, cost_eur=? WHERE id=?", (run.calls_used, run.cost_eur, run.run_id))
        self.check_thresholds(run_id=run.run_id)
        return cost

    def record_external(self, *, approval_id: str, agent: str, amount_eur: float, note: str) -> None:
        self.db.execute(
            "INSERT INTO cost_records(ts, month, task_id, agent, model, kind, cost_eur, estimated, simulated, note)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (now_iso(), month_key(), None, agent, None, "external", amount_eur, 0, 0, f"{approval_id}: {note}"),
        )
        self.check_thresholds()

    def check_thresholds(self, run_id: str | None = None) -> None:
        month = month_key()
        scopes = {
            "api": (self.month_spend(("api", "tool")), self.cfg.monthly_api_eur, "API-Budget"),
            "total": (self.month_spend(("api", "tool", "external")), self.cfg.monthly_total_eur, "Gesamtbudget"),
        }
        for scope, (spent, limit, label) in scopes.items():
            ratio = spent / limit if limit else 1.0
            for threshold in sorted(self.cfg.warn_thresholds) + [1.0]:
                if ratio < threshold:
                    continue
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO budget_alerts(month, scope, threshold, ts) VALUES (?,?,?,?)",
                    (month, scope, threshold, now_iso()),
                )
                if cur.rowcount != 1:
                    continue
                if threshold >= 1.0:
                    self.events.emit(
                        "budget.exhausted",
                        f"{label} ausgeschöpft ({spent:.2f} € von {limit:.2f} €) – automatischer Stopp",
                        from_agent="finance", agent="finance", severity="critical", run_id=run_id,
                        data={"scope": scope, "spent_eur": spent, "limit_eur": limit, "automated": True},
                    )
                else:
                    self.events.emit(
                        "comm.message",
                        f"Budgetwarnung: {int(threshold * 100)} % des {label}s verbraucht ({spent:.2f} € von {limit:.2f} €)",
                        from_agent="finance", to_agent="ceo", severity="warning", run_id=run_id,
                        data={"kind": "budget.warning", "scope": scope, "threshold": threshold, "spent_eur": spent,
                              "limit_eur": limit, "comm_kind": "message", "automated": True},
                    )

    def exhausted(self) -> bool:
        return (
            self.month_spend(("api", "tool")) >= self.cfg.monthly_api_eur
            or self.month_spend(("api", "tool", "external")) >= self.cfg.monthly_total_eur
        )
