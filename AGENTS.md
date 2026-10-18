# Agenten, Verantwortlichkeiten und Regeln

Alle Agenten können dasselbe Modell nutzen. Entscheidend sind Aufgabenart, Ausgabeschema, Werkzeuge und Schreibrechte.
Werkzeuge und Schreibrechte setzt `config/security.toml` durch. Die Zuständigkeit für Aufgabenarten prüft der Orchestrator.
Eine Aufgabe, deren Art nicht zur Rolle passt, schlägt fehl. Deshalb kann der CEO keine Spezialaufgaben selbst übernehmen.

| # | Agent | Rolle | Gruppe | Aufgabenarten | Werkzeuge | Schreibt nach |
|---|---|---|---|---|---|---|
| 1 | **Atlas** | CEO / Executive Orchestrator | Management | `ceo_review`, `ceo_decision`, `final_decision` | Workspace, Aufgabenverwaltung | `ceo/`, `reports/` |
| 2 | **Scout** | Research & Market Intelligence | Research & Strategy | `market_research` | **Websuche**, Workspace | `research/` |
| 3 | **Vector** | Business Strategy & Opportunity Evaluation | Research & Strategy | `idea_evaluation` | Workspace | `strategy/` |
| 4 | **Ledger** | CFO / Finance & Unit Economics | Research & Strategy | `finance_assessment` | Workspace | `finance/` |
| 5 | **Compass** | Product Manager & Customer Research | Product & Engineering | `mvp_spec` | Workspace | `product_spec/` |
| 6 | **Forge** | Software Engineer / Builder | Product & Engineering | `build` | Workspace, statische Prüfungen | `builder/`, `product/`, `site/` |
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
| MVP bauen | Builder | Programm (Pfade, statische Prüfungen), QA-Test |
| Positionierung | Marketing | Programm (Werbeaussagen), CEO-Review |
| Preis | Finance | Programm |
| Landingpage | Builder | QA-Compliance |
| Kundengewinnung | Sales | Programm (Rechtsgrundlagen), CEO-Review |
| Launch vorbereiten, Freigaben beantragen | Operations | CEO-Review, **Eigentümer** (Freigaben) |
| Messplan, Auswertungen | Analytics | Programm (keine erfundenen Kennzahlen) |
| Experimente | Marketing | **Eigentümer** (Veröffentlichung/Ausgaben) |
| Abschlussentscheidung | **CEO** | Eigentümer (Bericht) |

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
