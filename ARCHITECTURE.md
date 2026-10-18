# Architektur

```
┌────────────────────────── Control-Center (React + TS, frontend/) ──────────────────────────┐
│ Unternehmenskarte · Aktivitätsprotokoll · Agenten-/Verbindungsdetails · Freigabezentrum ·   │
│ Aufgaben · Ziele & Meilensteine · Kennzahlen · Kosten · Dateien                             │
└───────────────▲ REST (Bearer-Token) ─────────────────▲ SSE /api/events/stream (Last-Event-ID)┘
                │                                       │
┌───────────────┴────────────── FastAPI (src/aicompany/api/app.py) ───────────────────────────┐
│ Auth · TrustedHost · Security-Header · RunManager (Hintergrundlauf) · Datei-Ansicht (Text)  │
└───────┬───────────────┬───────────────┬─────────────────┬──────────────────┬───────────────┘
        │               │               │                 │                  │
  state.py        orchestrator.py   approvals.py      control.py         reports.py
  (Snapshot)      (CEO-Ablauf)      (Freigaben)       (Pause/Stopp)      (Berichte)
        │               │   │   │         │
        │        tasks.py  budget.py  processing.py/checks.py/scoring.py/finance.py
        │               │   │                  │
        │        llm/mock.py | llm/openai_backend.py (OpenAI Agents SDK)
        │               │
┌───────┴───────────────┴──────────── SQLite (data/<modus>/company.db, WAL) ──────────────────┐
│ tasks · events · runs · cost_records · budget_alerts · approvals · audit_log · control ·    │
│ agent_control · metrics · decisions · ideas · artifacts · meta                              │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
        Workspace (data/<modus>/workspace/<agent-ordner>/…) – einzige beschreibbare Dateiablage
```

## Module

| Modul | Aufgabe |
|---|---|
| `config.py` | `settings.toml` + `.env` → validierte `Settings` (Limits, Modelle, Preise, Uhr, Server) |
| `security.py` | `SecurityPolicy` (aus `security.toml`, Default-Deny), `Sandbox` (Pfadprüfung, Schreibrechte je Agent, Symlink-Schutz), `Redactor` (Geheimnisse) |
| `db.py` | Schema, Verbindungen pro Zugriff, `BEGIN IMMEDIATE`-Transaktionen, Audit-Log |
| `events.py` | Zentraler, persistenter Ereignisstrom; Kommunikationsereignisse brauchen Absender **und** Empfänger |
| `tasks.py` | Aufgaben mit Zustandsmaschine, Duplikatschutz per Key, atomare Übernahme (`claim`), Wiederanlauf, Blockadenweitergabe |
| `budget.py` | Preise, Schätzung vor dem Aufruf, Reservierungen bei Parallelität, Erfassung danach, Warnschwellen, harter Stopp |
| `agents/roles.py` | 11 Rollen: Mission, Verantwortlichkeiten, Regeln, zuständige Aufgabenarten |
| `agents/schemas.py` | Strukturierte Ausgaben (strict-JSON-kompatibel) je Aufgabenart |
| `llm/` | Austauschbare Backends: `MockBackend` (Dry-Run, Fehlerinjektion) und `OpenAIAgentsBackend` |
| `workflow.py` | Phasen, 20 Aufgabenvorlagen mit Abhängigkeiten, Meilensteine, Experimentuhr |
| `orchestrator.py` | Geschäftslauf: Lock, Wiederanlauf, CEO-Review, parallele Batches, Retries, Validierung, Überarbeitung, Handler |
| `processing.py`, `checks.py` | Inhaltliche Validierung (Quellen, Kennzahlen, Werbeaussagen, Pfade) und statische Codeprüfungen |
| `scoring.py`, `finance.py` | Transparente Punktzahl + Auswahlregeln; Break-even/Szenarien |
| `approvals.py`, `actions.py` | Freigabeanträge, Hash-Bindung, idempotente Ausführung, ehrliche Ausführer |
| `control.py` | Flags `paused`, `stop_new_tasks`, `shutdown`, Pausen je Agent |
| `state.py`, `reports.py` | Snapshot für UI/CLI und Managementberichte, ausschließlich aus DB-Daten |
| `scheduler.py`, `cli.py`, `preflight.py` | Begrenzter Scheduler, Kommandozeile, Live-Startsperre |

## Ablauf eines Geschäftslaufs (`Orchestrator.run_once`)

1. **Lock**: In einer Transaktion wird geprüft, ob ein anderer Lauf mit frischem Heartbeat aktiv ist (dann `RunActive`).
   Läufe mit veraltetem Heartbeat werden als `crashed` markiert, und ihre Aufgaben gehen zurück auf `pending`.
2. **Vorprüfungen**: Steuerflags, Experimentende, Budget. Beim ersten Lauf wird der Workflow angelegt.
3. Fällige genehmigte Freigaben werden ausgeführt (nur wenn nicht pausiert).
4. **Schleife**: Blockaden weitergeben → CEO-Review, falls Ergebnisse vorliegen (oder einmal pro Lauf zur Priorisierung)
   → ausführbare Aufgaben (Abhängigkeiten erfüllt, Agent nicht pausiert, Experimenttag erreicht) → Batch bis
   `concurrency` parallel. Während des Batches werden alle 0,5 s Heartbeat und Stopp-Flag geprüft.
5. **Aufgabe**: atomarer `claim` → Ereignisse `comm.assignment` (CEO → Agent) und `comm.handoff` (Lieferant → Agent)
   → Kontext aus Abhängigkeiten (gekürzt aufs Tokenlimit) → Kostenschätzung und Reservierung → Aufruf mit Retries
   → Kostenerfassung → Validierung → Handler (Scorecards, Finanzrechnung, Dateien, Freigabeanträge, QA-Rückgaben,
   CEO-Auswahlregeln) → `review` → `completed` (oder CEO-Review).
6. **Ende**: Meilensteine, Managementbericht, Laufdatensatz, Ereignis `run.finished`.

## Aufgabenzustände

```
pending ──claim──► in_progress ──► review ──► completed
   ▲                  │   │           │            │
   │  Retry/Überarb.  │   └► failed ◄─┘            │ QA/CEO-Rückgabe (begrenzt)
   └──────────────────┴──────────────── pending ◄──┘
pending ──► blocked (Abhängigkeit fehlgeschlagen) ──Retry durch Eigentümer──► pending
```

Erlaubte Übergänge stehen in `tasks.ALLOWED_TRANSITIONS`; alles andere wirft `InvalidTransition`.
Jede Aufgabe enthält ID, Key, Verantwortlichen, Ziel, Beschreibung, Eingaben, Abhängigkeiten, Ausgabeformat,
Akzeptanzkriterien, Priorität, Status, geschätzte/tatsächliche Kosten, Ergebnis, Dateien, Verlauf und Feedback.

## Live-Daten im Control-Center

- `GET /api/state` liefert einen Snapshot, der vollständig aus der Datenbank abgeleitet wird. Agentenstatus ergeben sich aus Aufgaben,
  Freigaben und Ereignissen. „Kommuniziert“ erscheint nur, wenn der Agent in den letzten 10 s tatsächlich gesendet hat.
- `GET /api/events/stream` (SSE) liest prozessübergreifend aus SQLite (`id > cursor`). Deshalb erscheinen auch Läufe aus
  CLI oder Scheduler live. Beim Wiederverbinden setzt der Browser `Last-Event-ID`; der Client dedupliziert zusätzlich nach ID
  und lädt nach jedem Abbruch Snapshot und fehlende Ereignisse nach.
- Kartenverbindungen entstehen ausschließlich aus `comm.*`-Ereignissen. Animiert sind nur Verbindungen mit einem
  Ereignis in den letzten 12 s. Abhängigkeiten werden getrennt, gestrichelt und ohne Animation dargestellt.
- Fehlen Daten, zeigt die Oberfläche „Noch keine Daten“ bzw. „Wartet auf ersten Lauf“. Bei Verbindungsverlust erscheint
  „Daten veraltet (Stand …)“.

## Austauschbarkeit

- **Modelle**: pro Agent in `settings.toml` (`[agents.<id>] model = …`), Preise unter `[pricing.<modell>]`.
- **Backend**: alles, was `LLMBackend.run(AgentCall) -> AgentCallResult` implementiert.
- **Agenten/Aufgaben**: Rolle in `agents/roles.py`, Schema in `agents/schemas.py`, Vorlage in `workflow.py`, optionaler Handler `_handle_<kind>`.
- **Externe Aktionen**: Parameterschema und Ausführer in `actions.py` (z. B. ein echter Hosting-Anbieter statt `local_release`).
