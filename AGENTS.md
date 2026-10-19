# Agenten, Verantwortlichkeiten und Regeln

Alle Agenten können dasselbe Modell nutzen. Zusätzlich zu den unten genannten Aufgabenarten kann jeder Agent `consultation` (Kollegenhilfe) übernehmen. Entscheidend sind Aufgabenart, Ausgabeschema, Werkzeuge und Schreibrechte.
Werkzeuge und Schreibrechte setzt `config/security.toml` durch. Die Zuständigkeit für Aufgabenarten prüft der Orchestrator.
Eine Aufgabe, deren Art nicht zur Rolle passt, schlägt fehl. Deshalb kann der CEO keine Spezialaufgaben selbst übernehmen.

| # | Agent | Rolle | Gruppe | Aufgabenarten | Werkzeuge | Schreibt nach |
|---|---|---|---|---|---|---|
| 1 | **Atlas** | CEO / Executive Orchestrator | Management | `ceo_review`, `ceo_decision`, `final_decision` | Workspace, Aufgabenverwaltung | `ceo/`, `reports/` |
| 2 | **Scout** | Research & Market Intelligence | Research & Strategy | `market_research` | **Websuche**, Workspace | `research/` |
| 3 | **Vector** | Business Strategy & Opportunity Evaluation | Research & Strategy | `idea_evaluation` | Workspace | `strategy/` |
| 4 | **Ledger** | CFO / Finance & Unit Economics | Research & Strategy | `finance_assessment` | Workspace | `finance/` |
| 5 | **Compass** | Product Manager & Customer Research | Product & Engineering | `mvp_spec` | Workspace | `product_spec/` |
| 6 | **Forge** | Software Engineer / Builder | Product & Engineering | `tech_design`, `implement`, `build` | Werkbank (Dateien, Tests), statische Prüfungen | `builder/`, `product/`, `site/` |
| 7 | **Echo** | Marketing & Brand Strategy | Marketing & Revenue | `positioning`, `experiment_plan` | Workspace, Freigabeanträge | `marketing/` |
| 8 | **Bridge** | Sales & Customer Acquisition | Marketing & Revenue | `sales_plan` | Workspace, Freigabeanträge | `sales/` |
| 9 | **Pulse** | Operations & Automation | Operations | `ops_plan` | Workspace, Freigabeanträge | `operations/` |
| 10 | **Sentinel** | QA, Risk & Compliance | Product & Engineering | `qa_review` | Workspace, statische Prüfungen | `qa/` |
| 11 | **Lens** | Analytics & Growth Optimization | Marketing & Revenue | `analytics_review` | Workspace, Messwerte lesen | `analytics/` |

## Verantwortungsmatrix (Workflow)

| Schritt | Verantwortlich | Prüft / entscheidet |
|---|---|---|
| Geschäftsmöglichkeiten recherchieren | Research | QA (Quellen), Programm (Quellenpflicht) |
| Modelle vergleichen und bewerten | Strategy | Programm (Punktzahl), QA |
| Wirtschaftlichkeit | Finance | Programm (Break-even), QA |
| Idee auswählen | **CEO** | Programm (Auswahlregeln) |
| MVP definieren | Product | CEO-Review |
| Technisches Design | Builder | Programm (Dateiplan, Testplan) |
| Software entwickeln | Builder | Programm (Codeprüfung, Tests wie eine CI), QA-Code-Review |
| Positionierung | Marketing | Programm (Werbeaussagen), CEO-Review |
| Preis | Finance | Programm |
| Landingpage | Builder | QA-Compliance |
| Kundengewinnung | Sales | Programm (Rechtsgrundlagen), CEO-Review |
| Launch vorbereiten, Freigaben beantragen | Operations | CEO-Review, **Eigentümer** (Freigaben) |
| Messplan, Auswertungen | Analytics | Programm (keine erfundenen Kennzahlen) |
| Experimente | Marketing | **Eigentümer** (Veröffentlichung/Ausgaben) |
| Zyklusentscheidung (weiter / Kurswechsel / neue Nische) | **CEO** | Programm plant den nächsten Zyklus; Eigentümer liest den Bericht |

### Laufender Betrieb (jeder weitere Zyklus nach `continue`)

| Aufgabe | Verantwortlich | Prüft / entscheidet |
|---|---|---|
| Kennzahlen auswerten | Analytics | Programm (nur echte Messwerte des Zyklus) |
| Verbesserungen planen | Product | CEO-Review |
| Neue Version bauen | Builder | Programm (statische Prüfungen), QA-Test mit Rückgabe |
| Content und Kampagnen | Marketing | Eigentümer (Veröffentlichung, Ausgaben) |
| Vertrieb und Anfragen | Sales | Programm (Rechtsgrundlagen) |
| Betrieb und Release | Operations | Eigentümer (Freigabe der Veröffentlichung) |
| Monatsabschluss | Finance | Programm |
| Zyklusentscheidung | CEO | Programm plant den nächsten Zyklus |

## Software-Team (Builder)

Der Builder arbeitet wie ein Entwicklungsteam mit fester, gut hostbarer Projektstruktur:
`app/main.py` (FastAPI), `app/*.py`, `app/static/*`, SQLite, `tests/test_*.py`, `requirements.txt`, `README.md` und
`Dockerfile`.

1. **Technisches Design** (`tech_design`): Architektur, Datenmodell, API-Endpunkte, Dateiplan, Testplan.
2. **Entwickeln** (`implement`): Der Builder nutzt die Werkzeuge `list_files`, `read_file`, `write_file`,
   `delete_file` und `run_tests`, bis alle Tests grün sind. Im Live-Modus sind das echte SDK-Function-Tools mit bis zu
   `builder.max_turns` Arbeitsschritten.
3. **CI durch das Programm:** Pflichtdateien, Codeprüfung und ein eigener, autoritativer Testlauf. Rote Tests schicken die
   Arbeit mit der Testausgabe zurück.
4. **Code-Review durch QA:** QA bekommt den Code und das Testergebnis. Befunde gehen mit Korrektur- und Testvorschlag
   zurück, und ein Kollege bietet Hilfe an.
5. **Release:** Operations beantragt `deploy_app`. Nach deiner Freigabe entsteht ein Release-Paket mit Dockerfile. Das
   automatische Ausrollen zu einem Hoster ist der nächste Ausbauschritt.

Im laufenden Betrieb entwickelt der Builder die bestehende Software weiter: Code lesen, ändern, Tests ergänzen.

## Teamarbeit zwischen den Agenten

Die Agenten arbeiten nicht nur nacheinander ab, sondern unterstützen sich gegenseitig:

| Mechanismus | Ablauf | Durchsetzung im Programm |
|---|---|---|
| **Hilfeanfrage** | Jedes Ergebnis kann bis zu 2 `help_requests` an Kollegen enthalten (z. B. Marketing fragt Finance nach dem realistischen Preisrahmen). | Für jede Anfrage entsteht eine Aufgabe `consultation` beim Kollegen; Ereignisse `comm.help_request` und `comm.help_answer`. |
| **Warten auf Zuarbeit** | Ist eine Anfrage `blocking`, legt der Agent sein Ergebnis zurück und macht nach der Antwort weiter. | Abhängigkeit auf die Hilfeaufgabe, höchstens `max_blocking_help_per_task` Runden; zählt nicht als Überarbeitung. |
| **Hilfe anbieten** | Wird Arbeit zur Überarbeitung zurückgegeben, bietet ein fachlich passender Kollege von sich aus Unterstützung an (z. B. Product hilft dem Builder nach einem QA-Befund). | Zuordnung in `Orchestrator.HELPERS`, nie der Kritiker selbst; Ereignis `comm.help_offer`. |
| **Teamwissen** | Antworten von Kollegen bekommt der Agent als `team_notes` in jeden weiteren Auftrag des Zyklus. | Kontextaufbau im Orchestrator. |

Grenzen: höchstens `max_consultations_per_run` Hilfeaufgaben pro Lauf (Standard 4). Jede Hilfeaufgabe ist ein normaler,
budgetierter Agentenaufruf. Schlägt eine Hilfe fehl, arbeitet der Agent ohne sie weiter und wird nicht blockiert.
Abschaltbar über `[collaboration] enabled = false`.

## Regeln für alle Agenten (im Prompt **und** im Programm)

| Regel | Durchsetzung im Programm |
|---|---|
| Keine erfundenen Quellen | Fakten ohne Quelle → Überarbeitung; im Live-Modus Abgleich der Quell-URLs mit den tatsächlich von der Websuche gelieferten URLs |
| Keine erfundenen Kennzahlen | Analytics-Werte müssen exakt in der `metrics`-Tabelle existieren; ohne Daten ist „data_available=true“ unzulässig |
| Keine erfundenen Testimonials / Erfolgsversprechen | Regex-Prüfung in Marketing-, Sales- und Build-Ausgaben |
| Externe Aktionen nur als Antrag | Agenten haben kein Werkzeug für externe Aktionen; `external_actions` werden zu Freigabeanträgen |
| Kein Dateizugriff außerhalb des eigenen Ordners | `Sandbox.check_write` (Pfad, Ordner, Symlinks) |
| Keine Geheimnisse | `Redactor` auf allen Ereignissen, Dateien, Freigaben und Dateiansichten |
| Begrenzte Überarbeitung | max. 2 Überarbeitungen, danach `failed` + Eskalation an CEO/Eigentümer |
| QA schlägt Korrekturen vor | Ein „fail“ ohne Befund oder ein Befund ohne Korrekturvorschlag ist ungültig |
| CEO wählt nicht allein nach Punktzahl | `scoring.check_selection`: Mindestpunktzahl, Finance- und QA-Review, keine kritischen Befunde, ≤ 3 Informationslücken |
