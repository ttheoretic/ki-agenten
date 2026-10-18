# Beispiel: vollständiger Dry-Run-Geschäftslauf

Erzeugt mit `aicompany demo` am 2026-10-18. Alle Agentenantworten sind **simuliert** (Dry-Run-Backend); die Kosten sind aus simulierten Tokenzahlen berechnet. Der Ablauf, die Limits, Überarbeitungen, Freigabeanträge und Berichte sind dagegen echt vom Programm erzeugt.

## Konsolenausgabe

```text
DRY-RUN in /home/user/ki-agenten/data/demo – alle Agentenantworten sind simuliert, es entstehen keine API-Kosten.
R-20261018231919-45be: completed | Tag 1 | 20 Aufrufe | 0.0811 € | Limit von 20 Agentenaufrufen pro Lauf erreicht
  abgeschlossen: p1.research.opportunities, p1.strategy.evaluate, p1.finance.unit_economics, p1.qa.selection_review, p1.ceo.select_idea, p2.product.mvp_spec, p2.builder.product, p3.marketing.positioning, p2.builder.product, p3.finance.pricing, p2.qa.product_test, p3.sales.acquisition, p3.builder.landing, p3.qa.compliance
  Bericht: workspace/reports/bericht-20261018-231920-815020.md
R-20261018231920-c7ac: completed | Tag 6 | 4 Aufrufe | 0.0058 € | Wartet auf Experimenttag 22 (heute Tag 6)
  abgeschlossen: p3.ops.launch_prep, p4.analytics.measurement, p4.marketing.experiments
  Bericht: workspace/reports/bericht-20261018-231921-150963.md
R-20261018231921-7c70: completed | Tag 11 | 0 Aufrufe | 0.0000 € | Wartet auf Experimenttag 22 (heute Tag 11)
  Bericht: workspace/reports/bericht-20261018-231921-208745.md
R-20261018231921-47a6: completed | Tag 16 | 0 Aufrufe | 0.0000 € | Wartet auf Experimenttag 22 (heute Tag 16)
  Bericht: workspace/reports/bericht-20261018-231921-268421.md
R-20261018231921-2a81: completed | Tag 21 | 0 Aufrufe | 0.0000 € | Wartet auf Experimenttag 22 (heute Tag 21)
  Bericht: workspace/reports/bericht-20261018-231921-325228.md
R-20261018231921-aa8a: completed | Tag 26 | 1 Aufrufe | 0.0013 € | Wartet auf Experimenttag 27 (heute Tag 26)
  abgeschlossen: p4.analytics.midtest
  Bericht: workspace/reports/bericht-20261018-231921-458121.md
R-20261018231921-5dbd: completed | Tag 30 | 3 Aufrufe | 0.0038 € | Alle Aufgaben abgeschlossen
  abgeschlossen: p5.analytics.final, p5.finance.final, p5.ceo.final_decision
  Bericht: workspace/reports/bericht-20261018-231921-715441.md

Offene Freigaben: 3. Control-Center: aicompany serve --data-dir /home/user/ki-agenten/data/demo
```

## Was in diesem Lauf passiert ist

- Lauf 1 stößt an das Limit von 20 Agentenaufrufen pro Geschäftslauf und endet geordnet; Lauf 2 setzt an derselben Stelle fort.
- QA (Sentinel) lehnt den ersten MVP-Build ab (fehlende Eingabevalidierung); der Builder (Forge) liefert eine überarbeitete Version, die QA erneut prüft.
- Der CEO (Atlas) gibt die erste Positionierung zur Überarbeitung an Marketing (Echo) zurück.
- Die Ideenauswahl wird zusätzlich durch Programmregeln geprüft (Mindestpunktzahl, Finance- und QA-Review).
- Operations und Marketing beantragen drei externe Aktionen (Website veröffentlichen, LinkedIn-Beitrag, 15-€-Anzeigentest). Ohne Freigabe wird nichts davon ausgeführt.
- Analytics meldet ehrlich „keine Daten“, weil keine echten Messwerte erfasst wurden; der CEO entscheidet deshalb auf Fortführung mit Markttest.

## Abschließender Managementbericht

### Managementbericht nach Lauf

Erstellt: 2026-10-18 23:19 UTC  
Modus: **DRY-RUN (simulierte Agentenantworten)**  
Lauf: `R-20261018231921-5dbd`  

> **Hinweis:** Dry-Run – alle Agentenergebnisse und Kosten sind simuliert.

#### Gesamtstatus

- Ziel: Innerhalb von 30 Tagen ein digitales Geschäftsmodell finden, das mit KI-Agenten weitgehend autonom betrieben werden kann, wenig Startkapital braucht, keine Lagerbestände voraussetzt und realistische Chancen auf erste zahlende Kunden bietet.
- Unternehmensstatus: **running**
- Experimenttag: 30/30 (Plan-Phase: Auswertung, Arbeitsphase: Auswertung)
- Fortschritt: 20/20 Aufgaben (100.0 %) – Formel: abgeschlossene Aufgaben / alle Aufgaben des Geschäftszyklus

#### Geschäftsmodell

**Angebots- & Stundensatzrechner mit Vorlagenpaket für Handwerksbetriebe** – 67.5 Punkte. Begründung: [SIMULIERT] Höchste Punktzahl, Finance und QA ohne kritische Befunde

| Idee | Punkte | Status |
|---|---|---|
| Angebots- & Stundensatzrechner mit Vorlagenpaket für Handwerksbetriebe | 67.5 | selected |
| DSGVO-Vorlagenpaket für Vereine | 58.5 | not_selected |
| Wöchentlicher Wettbewerbspreis-Report für kleine Onlineshops | 54.9 | not_selected |
| KI-Workflow für Sitzungsprotokolle in Vereinen | 48.8 | not_selected |
| Fördermittel-Vorabcheck für Kleinunternehmen | 45.9 | not_selected |

#### Meilensteine

- [x] M1 Geschäftsidee ausgewählt
- [x] M2 MVP gebaut und von QA bestätigt
- [x] M3 Marktvorbereitung abgeschlossen
- [x] M4 Markttest ausgewertet
- [x] M5 Abschlussentscheidung getroffen

#### Budget und Kosten

- API-Kosten diesen Monat: 0.0919 € von 30.00 €
- Gesamtausgaben: 0.0919 € von 100.00 € (verbleibend 99.91 €, davon gebunden durch Freigaben 0.00 €)
- Davon konservativ geschätzt (Verbrauch unbekannt): 0.0000 €
  - research / mock-model: 1 Aufrufe, 0.0250 €
  - qa / mock-model: 4 Aufrufe, 0.0117 €
  - ceo / mock-model: 7 Aufrufe, 0.0110 €
  - strategy / mock-model: 1 Aufrufe, 0.0101 €
  - builder / mock-model: 3 Aufrufe, 0.0091 €
  - finance / mock-model: 3 Aufrufe, 0.0088 €
  - marketing / mock-model: 3 Aufrufe, 0.0065 €
  - analytics / mock-model: 3 Aufrufe, 0.0036 €
  - product / mock-model: 1 Aufrufe, 0.0023 €
  - sales / mock-model: 1 Aufrufe, 0.0022 €
  - operations / mock-model: 1 Aufrufe, 0.0016 €

#### Einnahmen und Kennzahlen

- Umsatz: Noch keine Daten
- Kennzahlen: Noch keine Daten (Messwerte werden im Control-Center erfasst)

#### Letzte CEO-Entscheidungen

- 2026-10-18T23:19: Abschlussentscheidung: Fortführung
- 2026-10-18T23:19: CEO-Lagebesprechung #5: 1 akzeptiert, 0 zur Überarbeitung
- 2026-10-18T23:19: CEO-Lagebesprechung #4: 1 akzeptiert, 0 zur Überarbeitung
- 2026-10-18T23:19: CEO-Lagebesprechung #3: 1 akzeptiert, 0 zur Überarbeitung
- 2026-10-18T23:19: CEO-Lagebesprechung #2: 0 akzeptiert, 1 zur Überarbeitung
- 2026-10-18T23:19: CEO-Lagebesprechung #1: 1 akzeptiert, 0 zur Überarbeitung
- 2026-10-18T23:19: Geschäftsidee ausgewählt: Angebots- & Stundensatzrechner mit Vorlagenpaket für Handwerksbetriebe (67.5 Punkte)

#### Offene Freigaben

- A-ac5c57cc: Kleiner Anzeigentest (15 €) (paid_ads, 15.00 €) – Echo
- A-0249fd98: Fachbeitrag auf LinkedIn veröffentlichen (publish_content, 0.00 €) – Echo
- A-a507856f: Landingpage veröffentlichen (lokales Release-Paket) (publish_website, 0.00 €) – Pulse

#### Risiken und Blockaden

- (medium) [SIMULIERT] Impressum und Datenschutzerklärung enthalten Platzhalter → Vor Veröffentlichung durch den Eigentümer ausfüllen lassen

#### Nächste geplante Schritte

- keine ausführbaren Aufgaben
- CEO: [SIMULIERT] Kritischen Pfad fortsetzen
