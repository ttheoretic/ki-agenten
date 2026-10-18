# Budget und Kostenkontrolle

Alle Werte stehen zentral in `config/settings.toml` unter `[budget]`, `[models]`, `[pricing.*]`, `[agents.*]` und `[web_search]`.

| Limit | Standard | Durchsetzung |
|---|---|---|
| Monatliches Gesamtbudget | 100 € | API + externe Ausgaben + durch Genehmigungen gebundene Beträge; Genehmigungen über dem Restbudget werden abgewiesen |
| Monatliche API-Ausgaben | 30 € | Prüfung vor jedem Aufruf; bei Erreichen automatischer Stopp (`budget.exhausted`) |
| Kosten pro Geschäftslauf | 2 € | Prüfung vor jedem Aufruf inkl. Reservierungen paralleler Aufrufe |
| Agentenaufrufe pro Lauf | 20 | Auch Fehlversuche zählen (verhindert Endlos-Retries) |
| Überarbeitungen pro Aufgabe | 2 | danach `failed`, abhängige Aufgaben `blocked` |
| Versuche bei API-Fehlern | 2 pro Aufruf | exponentieller Backoff; danach endet der Lauf, die Aufgabe bleibt eingeplant |
| Tokenlimits | je Agent | `max_output_tokens` geht an das Modell; der Eingabekontext wird auf `max_input_tokens × 3` Zeichen gekürzt |
| Websuchen | 8 pro Lauf | danach wird das Werkzeug für den Rest des Laufs nicht mehr vergeben |
| Warnungen | 50 / 75 / 90 % | je Monat und Bereich (API, gesamt) genau einmal, als Nachricht Finance → CEO |

## Kostenberechnung

```
Kosten (EUR) = (Eingabetokens/1e6 × Eingabepreis + Ausgabetokens/1e6 × Ausgabepreis + Websuchen × Preis je Suche) × USD→EUR
```

- **Vor dem Aufruf**: konservative Schätzung mit Eingabe ≈ Zeichen/3 + 500 Tokens, volle Ausgabelänge und Unsicherheitsaufschlag 1,25.
  Die Schätzung wird reserviert, damit parallele Aufrufe die Limits nicht gemeinsam überschreiten.
- **Nach dem Aufruf**: tatsächliche Tokens aus `RunResult.context_wrapper.usage` und die Anzahl der Websuchen aus den Ergebnis-Items.
- **Unbekannter Verbrauch** (Fehlversuch, Abbruch, Schemafehler): Die Schätzung wird verbucht und als `estimated=1` markiert.
  Das Control-Center zeigt den geschätzten Anteil separat an.
- **Unbekanntes Modell**: Es gilt der teuerste konfigurierte Preis × 1,25. Im Live-Modus ist der Start ohne Preis gesperrt.
- **Eskalation** auf das stärkere Modell (`models.escalation`) erfolgt nur, wenn eine Aufgabe zweimal ungültige Ausgaben geliefert hat.

Kosten werden je Aufruf in `cost_records` gespeichert (Agent, Modell, Aufgabe, Lauf, Tokens, Websuchen, geschätzt/simuliert).
Im Dry-Run sind alle Kosten aus simulierten Tokenzahlen berechnet und als **simuliert** gekennzeichnet. Sie liegen in einer
eigenen Datenbank (`data/dry_run/`) und vermischen sich nie mit Live-Kosten.

## Preise (bitte prüfen)

| Modell | Eingabe $/1M | Ausgabe $/1M |
|---|---|---|
| gpt-5.4-mini (Standard) | 0,75 | 4,50 |
| gpt-5.4-nano | 0,20 | 1,25 |
| gpt-5.4 (Eskalation) | 2,50 | 15,00 |
| Websuche | 0,01 $ je Aufruf | |

Quelle: Drittanbieter-Übersichten (Stand Juni 2026), nicht die offizielle Preisseite. **Vor dem Live-Betrieb
mit https://openai.com/api/pricing abgleichen** und `settings.toml` anpassen.

## Wichtiger Hinweis

Ein anwendungseigenes Limit ist **keine absolute Garantie** gegen Abrechnungen des API-Anbieters, etwa bei abweichenden
Preisen, versteckten Reasoning-Tokens oder anderen Programmen mit demselben Schlüssel. Setze zusätzlich ein
**Ausgabenlimit (Usage Limit) im OpenAI-Konto** und nutze einen eigenen API-Schlüssel nur für dieses Projekt.
