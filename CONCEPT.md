# Konzept: Autonomes KI-Unternehmen

## 1. Was das System macht

Das System simuliert ein kleines digitales Unternehmen und betreibt es weitgehend selbstständig. Elf spezialisierte
KI-Agenten (CEO, Research, Strategy, Finance, Product, Builder, Marketing, Sales, Operations, QA, Analytics) arbeiten in
einem **30-Tage-Experiment** auf ein Ziel hin: ein digitales Geschäftsmodell finden, das mit KI-Agenten betreibbar ist,
wenig Startkapital braucht, keine Lagerbestände hat und realistische Chancen auf erste zahlende Kunden bietet.

Der Ablauf ist kein Skript, das blind durchläuft. Er besteht aus Aufgaben mit Abhängigkeiten, Akzeptanzkriterien,
Kostenschätzungen und Statusmodell. Ein CEO-Orchestrator verteilt sie, prüft Ergebnisse, gibt Mängel zurück und trifft
Entscheidungen nach dokumentierten Kriterien. Alles wird in SQLite gespeichert. Ein Neustart setzt deshalb an derselben
Stelle fort. Der Mensch (Eigentümer) beobachtet im **Live-Control-Center** und entscheidet nur dort, wo es nötig ist:
bei externen Aktionen, Ausgaben und Veröffentlichungen.

### Dauerbetrieb statt Einmal-Experiment

Die Geschäftsmodellsuche ist nur der Anfang. Das Unternehmen arbeitet danach in **Zyklen ohne festes Ende** weiter.
Jede Abteilung erledigt in jedem Zyklus ihre wiederkehrende Arbeit:

| Abteilung (Agent) | Laufender Betrieb (alle 14 Tage) |
|---|---|
| Analytics (Lens) | Kennzahlen auswerten, Hypothesen prüfen, Experimente vorschlagen |
| Product (Compass) | Verbesserungen aus Feedback und Zahlen planen |
| Builder (Forge) | Neue Produktversion bauen |
| QA (Sentinel) | Neue Version testen, Sicherheit und Compliance prüfen |
| Marketing (Echo) | Content und Kampagnen planen, Veröffentlichungen beantragen |
| Sales (Bridge) | Anfragen nachfassen, Einwände auswerten, Akquise verbessern |
| Operations (Pulse) | Betrieb und Kosten prüfen, Release beantragen |
| Finance (Ledger) | Monatsabschluss: Ist vs. Prognose, Preis und Kosten |
| CEO (Atlas) | Ergebnisse prüfen, priorisieren und am Zyklusende entscheiden |

**Zyklusentscheidung → nächster Zyklus (vom Programm automatisch geplant):**

| CEO-Entscheidung | Nächster Zyklus |
|---|---|
| `continue` (Nachfrage belegt oder Test noch nicht aussagekräftig) | Laufender Betrieb, 14 Tage |
| `pivot` (Nische trägt nicht, z. B. viel Reichweite, keine Käufe) | Kurswechsel: Strategy bewertet die vorhandene Recherche ohne die gescheiterte Idee neu, danach Bau, Markttest, Auswertung (30 Tage) |
| `stop` (Markt insgesamt ungeeignet) | Neue Nische: frische Recherche, alle bisher versuchten Ideen ausgeschlossen (30 Tage) |

Gescheiterte Ideen kommen in eine Sperrliste, die die Auswahlregeln durchsetzen. Lehren und frühere Entscheidungen
(„Unternehmensgedächtnis“) bekommen alle Agenten als Kontext mit. Messwerte zählen immer nur für den Zyklus, in dem sie
erhoben wurden. Als Sicherheitsgrenze hält das Unternehmen nach `max_cycles` (Standard 12) an und wartet auf den Eigentümer.

## 2. Untersuchte Geschäftsmodelle

Der Research-Agent untersucht mindestens fünf Nischen aus diesen Klassen (nur als Ausgangspunkt, nicht als Einschränkung):

| Modellklasse | Beispiel | Eignung für ein KI-Unternehmen |
|---|---|---|
| Digitale Produkte (Vorlagen, Rechner, Arbeitshilfen) | Angebots-/Stundensatzrechner für Handwerk | **sehr hoch**: einmal bauen, ohne Betreuung verkaufen, statisch hostbar |
| Micro-SaaS / spezialisierte Webanwendung | Fördermittel-Vorabcheck | hoch, aber Pflege, Support und ggf. Haftungsrisiken |
| Automatisierte Dienstleistungen für Unternehmen | Wettbewerbspreis-Report | hoch automatisierbar; Datenquellen und Nutzungsbedingungen prüfen |
| Recherche- und Berichtsdienste | Branchen-Wochenreport | gut, solange Quellen legal nutzbar sind |
| KI-Workflow-Werkzeuge | Protokoll-Automation | mittel: oft personenbezogene Daten (DSGVO-Risiko) |
| Nischenprodukte für klar definierte Zielgruppen | DSGVO-Vorlagen für Vereine | gut umsetzbar; Rechtsberatungsnähe ist ein Risiko |

**Am besten passen** nach den Kriterien des Auftrags **digitale Produkte und kleine, statische Werkzeuge für klar
umrissene B2B-Nischen**: keine Lagerbestände, Kosten nahe null, hoher Automatisierungsgrad, kaum Kundenbetreuung und
ein klarer Preisanker. Recherche- und Berichtsdienste folgen knapp dahinter. Modelle mit personenbezogenen Daten,
Rechtsberatungsnähe oder hohem Werbebedarf bekommen im Risikokriterium Abzüge.

Die tatsächliche Auswahl trifft das System selbst über das **Punktesystem (0–100)**:

| Kriterium | Punkte |
|---|---|
| Nachweisbare Nachfrage | 20 |
| Zahlungsbereitschaft | 15 |
| Automatisierbarkeit | 15 |
| Niedrige Start- und Betriebskosten | 15 |
| Einfachheit der Kundengewinnung | 10 |
| Technische Umsetzbarkeit | 10 |
| Skalierbarkeit | 5 |
| Wettbewerbsvorteil | 5 |
| Geringes rechtliches/operatives Risiko | 5 |

Der Strategy-Agent bewertet jedes Kriterium mit 0–1, mit Beleg und Konfidenz. Die Punktzahl berechnet das **Programm**,
nicht das Modell. Eine Idee wird nur ausgewählt, wenn zusätzlich harte Regeln erfüllt sind: Mindestpunktzahl,
unabhängiger Finance- und QA-Review, kein kritischer QA-Befund und nicht zu viele Informationslücken.

## 3. Zusammenarbeit der Agenten

```
Research ──► Strategy ──► Finance ──► QA ──► CEO wählt Idee
                                              │
                         Product (MVP-Spec) ◄─┘
                          │            │
                    Builder (MVP)   Marketing (Positionierung) ──► Finance (Preis)
                          │                       │                     │
                     QA (Test) ◄── Rückgabe ──►  Builder (Landingpage) ◄─┘   Sales (Akquise)
                          └────────────► QA (Compliance) ◄────────────────────┘
                                              │
                                 Operations (Launch, Freigabeanträge)
                                              │
                     Analytics (Messplan) ─► Marketing (Experimente) ─► Analytics (Auswertung)
                                              │
                         Analytics + Finance (Abschluss) ─► CEO (Fortführen / Kurswechsel / Stopp)
```

- Unabhängige Aufgaben laufen **parallel**, z. B. MVP-Bau und Positionierung. Bis zu 3 Aufrufe laufen gleichzeitig, konfigurierbar.
- Abhängige Aufgaben laufen **sequenziell**. Ergebnisse werden als strukturierte Daten übergeben; jede Übergabe ist ein echtes Ereignis (`comm.handoff`).
- Der **CEO** prüft vorgelegte Ergebnisse (Produkt-Spec, Positionierung, Vertriebsplan, Launch-Plan), setzt Prioritäten,
  fordert gezielte Nachrecherche an (begrenzt) und gibt Mängel mit Begründung zurück.
- **QA** prüft unabhängig. Bei Fehlern geht die Aufgabe mit Korrektur- und Testvorschlag an den zuständigen Agenten zurück (`comm.feedback`).
- **Schleifenschutz**: höchstens 2 Überarbeitungen pro Aufgabe, 6 Ausführungsversuche, 2 Zusatzaufgaben insgesamt und
  20 Aufrufe pro Lauf. Danach schlägt die Aufgabe fehl, abhängige Aufgaben werden blockiert, und der Eigentümer entscheidet.

## 4. Automatisch vs. Freigabe

| Automatisch erlaubt | Nur mit menschlicher Freigabe | Immer verboten |
|---|---|---|
| Recherche (Websuche) | Website/Inhalte veröffentlichen | Shell-/Admin-Zugriff |
| Dateien im eigenen Workspace-Ordner | Externe Nachrichten senden | Zugriff außerhalb des Workspace |
| Statische Prüfungen von generiertem Code | Bezahlte Werbung, Käufe, Abos, Zahlungen | Weitergabe von Zugangsdaten |
| Interne Analysen, Aufgabenverwaltung | Verträge | Massenkommunikation (> 25 Empfänger) |
| Marketing-Entwürfe | Produktivsetzung kritischer Änderungen | Änderung der Sicherheitsrichtlinie |
| Auswertung vorhandener Messwerte | Verarbeitung sensibler personenbezogener Daten | Selbstständige Rechteerweiterung |

Diese Regeln stehen in `config/security.toml` und werden **im Programm** durchgesetzt (siehe `SECURITY.md`).
Unbekannte Aktionen gelten als verboten.

## 5. Technologien und externe Dienste

- Python 3.11–3.13, **OpenAI Agents SDK** (`openai-agents==0.24.0`), Pydantic, SQLite, FastAPI, Uvicorn, pytest
- React 19 + TypeScript + Vite für das Control-Center, Server-Sent Events für Live-Ereignisse
- **Erforderlich nur für den Live-Modus:** ein OpenAI-API-Konto mit Guthaben (`OPENAI_API_KEY`). Die Websuche läuft als
  gehostetes OpenAI-Werkzeug; ein weiterer Suchanbieter ist nicht nötig.
- **Optional, erst ab dem Markttest:** Domain und Hosting (z. B. ein statischer Hoster), ein Zahlungsanbieter
  (z. B. Stripe Payment Links oder Lemon Squeezy) und Webanalyse ohne Cookies. Das System bindet diese Dienste bewusst
  **nicht** automatisch an. Genehmigte Aktionen erzeugen ein lokales Release-Paket bzw. einen Outbox-Eintrag, und der Mensch
  führt sie aus.

## 6. Laufende Kosten (Schätzung)

| Posten | Schätzung |
|---|---|
| API (gpt-5.4-mini, ~20 Aufrufe à ~4k Eingabe / ~2,5k Ausgabe Tokens + 8 Websuchen) | ca. 0,30–0,40 € pro vollem Lauf |
| Kompletter 30-Tage-Zyklus (~35 Agentenaufrufe) | ca. 0,60–1,50 € API |
| Leerläufe (warten auf Experimenttag) | 0 € (keine Aufrufe) |
| Domain | ca. 1–2 €/Monat (optional) |
| Statisches Hosting | 0–5 €/Monat (optional) |
| Zahlungsanbieter | prozentuale Gebühr je Verkauf |
| Werbung | 0 € by default; jede Ausgabe nur per Freigabe |

Die Grenzen sind hart: 100 €/Monat gesamt, 30 €/Monat API, 2 €/Lauf, 20 Aufrufe/Lauf (siehe `BUDGET.md`). Die Preise
stammen aus Drittquellen (Stand Juni 2026) und **müssen vor dem Live-Betrieb geprüft werden**.

## 7. Grenzen und Risiken

- **Kein Gewinnversprechen.** Das System prüft Hypothesen. Erfolg hängt von realer Nachfrage ab, und die kann nur ein Markttest zeigen.
- **Modellqualität:** LLM-Recherchen können falsch sein. Gegenmaßnahmen: Quellenpflicht für Fakten, Abgleich mit tatsächlich
  von der Websuche gelieferten URLs, unabhängiger QA-Review und die Trennung von Fakt, Schätzung und Hypothese.
- **Der Markttest braucht den Menschen.** Veröffentlichung, Zahlungsabwicklung und Messdaten (Besucher, Verkäufe) entstehen
  außerhalb des Systems. Kennzahlen werden im Control-Center eingetragen; das System erfindet keine.
- **Rechtliches:** Impressum, Datenschutzerklärung, AGB und Steuern verantwortet der Eigentümer. QA markiert Platzhalter, ersetzt aber keine Rechtsberatung.
- **Kostenlimit:** Das App-Limit ist keine Garantie gegen Abrechnungen des Anbieters. Setze zusätzlich ein Limit im OpenAI-Konto.
- **Generierter Code** wird nicht ausgeführt, nur statisch geprüft. Das MVP ist bewusst eine statische Web-App.

## 8. Ablauf des 30-Tage-Experiments

| Phase | Tage | Inhalt | Meilenstein |
|---|---|---|---|
| 1 Recherche & Auswahl | 1–5 | Nischen, Bewertung, Finance- und QA-Review, CEO-Auswahl | M1 Idee ausgewählt |
| 2 Produktentwicklung | 6–12 | MVP-Spec, Bau, QA-Test mit Rückgaben | M2 MVP geprüft |
| 3 Marktvorbereitung | 13–17 | Positionierung, Preis, Landingpage, Vertrieb, Compliance, Launch-Anträge | M3 Launch vorbereitet |
| 4 Markttest | 18–26 | Freigaben → Veröffentlichung, Experimente, reale Messwerte | M4 Zwischenauswertung |
| 5 Auswertung | 27–30 | Hypothesen vs. Daten, Finanzabgleich, Fortführen/Kurswechsel/Stopp | M5 Abschlussentscheidung |

Die Phasen sind Planfenster. Liegt die Arbeit vor dem Plan, beginnt die Messung früher; die Auswertungen warten auf ihre
Tage (22 bzw. 27), damit genug Daten zusammenkommen. Der konkrete Betriebsplan steht in `docs/PLAN_30_TAGE.md`.
