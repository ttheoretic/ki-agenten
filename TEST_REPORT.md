# Testbericht

Stand: 2026-10-18 · Umgebung: Linux, Python 3.13, Node 22, Chromium 141 (Playwright 1.56.1)
Alle Tests laufen ohne API-Schlüssel und ohne API-Kosten (Dry-Run- bzw. Attrappen-Backend).

## Ergebnisse

| Suite | Befehl | Ergebnis |
|---|---|---|
| Backend (pytest) | `python -m pytest` | **125 bestanden**, 0 fehlgeschlagen (≈ 110 s) |
| Selbsttest (Live-Gate) | `aicompany selftest` | **bestanden**, Marker für den aktuellen Codestand geschrieben |
| Frontend-Logik (Vitest) | `cd frontend && npm test` | **14 bestanden** |
| Typecheck + Build | `npm run build` | erfolgreich (`tsc --noEmit`, Vite-Build) |
| End-to-End im Browser (Playwright) | `npx playwright test` | **2 bestanden** (echtes Backend im Dry-Run, Chromium) |
| Vollständiger Dry-Run | `aicompany demo --cycles 2` | Gründungszyklus (Tag 1 → 30) und anschließender Betriebszyklus laufen automatisch durch |
| Nischenwechsel | `scripts/record_preview.py` | Mit DEMO-Kennzahlen (420 Besucher, 0 Verkäufe) entscheidet der CEO „Kurswechsel“; Zyklus 2 wählt automatisch die nächstbeste Idee |
| Live-Preflight | `aicompany preflight` | ohne Schlüssel korrekt gesperrt; mit (Dummy-)Schlüssel und bestandenem Selbsttest „startbereit“ |

## Abdeckung der geforderten Testbereiche

| Anforderung | Tests (Auswahl) |
|---|---|
| Kostenlimits | `test_budget.py`: Aufruflimit 20/Lauf, Laufbudget, Monats-API-Budget mit hartem Stopp, Warnschwellen 50/75/90 % genau einmal, Erschöpfung → Lauf `budget_exhausted`, Reservierungen bei Parallelität, unbekanntes Modell/unbekannter Verbrauch konservativ |
| Aufgabenstatus und Übergaben | `test_tasks.py` (Zustandsmaschine, Abhängigkeiten, Experimenttag); `test_orchestrator.py::test_full_dry_run_cycle_completes` (Übergaben, QA- und CEO-Rückgaben, Meilensteine) |
| Wiederaufnahme nach Neustart | `test_resume_after_crash`, `test_recover_stale_tasks`, `test_events_survive_restart` |
| API-Ausfälle | `test_transient_api_errors_are_retried`, `test_api_outage_stops_run_and_keeps_task`, `test_openai_backend_maps_errors` |
| Ungültige Agentenausgaben | `test_invalid_output_goes_to_revision`, `test_semantically_invalid_output_rejected`, `test_fabricated_metrics_rejected`, `test_invalid_output_rejected_by_schema` |
| Dauerbetrieb und Nischenwechsel | `test_cycles.py`: weiter → Betriebszyklus mit allen Abteilungen, Kurswechsel nach Fehlschlag, neue Nische mit Ausschlussliste, Sperre bereits versuchter Ideen, `max_cycles`, Unternehmensgedächtnis im Agentenkontext, Messwerte pro Zyklus |
| Teamarbeit | `test_collaboration.py`: blockierende Hilfeanfrage wartet auf den Kollegen, Antworten erreichen den Anfragenden als Teamwissen, Hilfsangebot bei Rückgabe, Limit pro Lauf, abschaltbar, gescheiterte Hilfe blockiert nicht |
| Überarbeitungslimits / keine Endlosschleifen | `test_revision_limit_fails_and_blocks_dependents`, `test_followup_limit_prevents_loops`, `test_selection_rules_override_ceo`, `test_scheduler_is_bounded` |
| Berechtigungen | `test_security.py` (Sandbox, Ordnerrechte, Symlinks, Werkzeuge, Default-Deny), `test_ceo_cannot_execute_specialist_task`, `test_build_path_traversal_rejected`, `test_no_dangerous_tools_given` |
| Freigaben für externe Aktionen | `test_approvals.py` (15 Tests: verbotene/unbekannte Aktionen, Massenkommunikation, Hash-Bindung, Manipulation, Ablauf, Budget, manuelle Bestätigung, Pausensperre), `test_approval_flow_via_api`, E2E-Genehmigung |
| Schutz vertraulicher Daten | `test_redactor_masks_secrets`, `test_secrets_never_persisted` (DB-Datei + Workspace), `test_owner_token_not_in_events_or_files`, `test_file_access_is_sandboxed` |
| Doppelte Ausführung | `test_claim_prevents_double_execution`, `test_parallel_runs_are_locked`, `test_create_is_idempotent_by_key`, `test_duplicate_requests_are_deduplicated`, `test_approve_executes_exactly_once` |
| Live-Modus erst nach Tests | `test_live_mode_blocked_without_selftest_and_key`, `test_live_mode_requires_current_code`, `test_unpriced_model_blocks_live` |
| UI: reale Agentenstatus | `test_initial_state_has_no_fake_data`, `test_state_reflects_real_status`; E2E prüft `data-status` der Knoten vor/nach dem Lauf |
| UI: Aufgabenübergaben | `graph.test.ts` (Kanten nur aus `comm.*`, aktiv nur bei frischen Ereignissen, Abhängigkeiten getrennt); E2E: Klick auf Kante CEO↔Research zeigt Absender/Anlass |
| UI: Aktualisierung bei Ereignissen | `live.test.ts`; E2E: Lauf über Button → Feed, Statuswechsel, ausgewählte Idee erscheinen live |
| UI: Wiederverbindung | `live.test.ts::verbindet nach Abbruch neu…` (Backoff, Nachladen ab letzter ID), `test_sse_stream_and_reconnect` (Last-Event-ID, keine Duplikate), `store.test.ts` (Deduplizierung) |
| Persistenz des Aktivitätsprotokolls | `test_events_persist_and_paginate`, `test_events_survive_restart` |
| Offene Freigaben / Genehmigen / Ablehnen | `test_approval_flow_via_api`; E2E: Genehmigen mit Bestätigung → „Genehmigt“ + „Erfolgreich ausgeführt“, zweite Genehmigung → 409 |
| Pause/Stopp | `test_pause_prevents_dispatch`, `test_paused_agent_is_skipped`, `test_stop_cancels_running_calls`, `test_stop_new_lets_running_finish`, `test_control_endpoints`; E2E: Pausieren sperrt „Lauf starten“ |
| Fehlerzustände / fehlende Daten | `test_retry_failed_task` (Status `attention`, Agent `error`, Retry), `test_auth_required`, `test_untrusted_host_rejected`, `live.test.ts::offline`; E2E: „Noch keine Daten“ für Umsatz, Fortschritt, Kennzahlen |

## Während der Tests gefundene und behobene Fehler

1. **Hash-Abweichung bei ganzzahligen Beträgen**: Ein Freigabeantrag mit `cost_eur=15` (int) hatte einen anderen Hash als nach dem Laden aus SQLite (`15.0`), sodass die Genehmigung fälschlich als Manipulation abgewiesen wurde. Behoben durch Normalisierung auf `float`.
2. **Scheduler konnte endlos warten** (Tageslimit/Pause ohne Lauf). Behoben mit `max_idle_cycles`.
3. **Pfadprüfung nach Typprüfung**: Ein `../escape.sh` wurde nur als „falscher Dateityp“ statt als Sicherheitsverstoß gemeldet. Die Pfadprüfung läuft jetzt zuerst.
4. **Live-Aktualisierung im Browser**: `setTimeout` wurde mit fremdem `this` aufgerufen („Illegal invocation“). Der Fehler wurde verschluckt, und der Snapshot aktualisierte sich nur alle 10 s. Gefunden durch den E2E-Test; behoben mit Wrapper-Funktionen und einer Sequenzprüfung gegen veraltete Antworten.
5. **Token per Link bei bereits geöffneter Seite** wurde ignoriert. Behoben durch `hashchange`-Listener.
6. **Doppelte Lauf-IDs** bei sehr schnell aufeinanderfolgenden Läufen (4 Hex-Zeichen pro Sekunde). Jetzt 8 Hex-Zeichen.
7. **Meilenstein des beendeten Zyklus fehlte**, weil die Abschlussentscheidung den neuen Zyklus startet, bevor die Meilensteine geprüft werden. Jetzt wird der gerade beendete Zyklus mitgeprüft.
8. **Status „versucht“ ging verloren**, wenn im neuen Zyklus eine Idee ausgewählt wurde. Behoben.

## Was fehlt / bekannte Grenzen

- **Kein Test gegen die echte OpenAI-API.** In dieser Umgebung gab es keinen Schlüssel. Das Live-Backend ist gegen die
  tatsächlichen SDK-Klassen (`Agent`, `ModelSettings`, `WebSearchTool`, `ModelBehaviorError`) mit einer Attrappe von
  `Runner.run` getestet: Agentenaufbau, Usage-Auswertung, Zitat-URLs, Fehlerzuordnung. Erster echter Lauf: siehe README, „Live-Betrieb“.
  Zu prüfen ist dabei vor allem, ob `web_search_call.action.sources` mit dem gewählten Modell befüllt wird; sonst greift nur der Abgleich über `url_citation`.
- **Modellpreise** stammen aus Drittquellen und sind vor dem Live-Betrieb zu prüfen.
- **Externe Ausführer** sind bewusst minimal: Website → lokales Release-Paket, Nachricht → lokaler Postausgang, alles
  Kostenpflichtige → `manual_required`. Echte Anbieter (Hosting-API, SMTP, Zahlungen) sind nicht angebunden.
- **Kennzahlen** kommen nur aus manueller Eingabe (UI/API); eine Webanalyse- oder Zahlungsanbieter-Anbindung fehlt.
- **Generierter Code** wird nur statisch geprüft, nicht ausgeführt (Absicht). Funktionstests des MVP macht QA durch Codeprüfung, nicht im Browser.
- **Ein Owner-Token, keine Benutzerrollen.** Für den Betrieb außerhalb von localhost sind ein Reverse-Proxy mit TLS und zusätzliche Authentifizierung nötig.
- **Dry-Run-Inhalte** sind deterministische Platzhalter. Sie prüfen den Ablauf, nicht die Qualität echter Agentenarbeit.
