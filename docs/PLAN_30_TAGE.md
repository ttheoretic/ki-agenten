# Konkreter Plan für die ersten 30 Tage

Rollen: **Du** = Eigentümer (Mensch), **System** = Agenten + Orchestrator. Standardtakt: Scheduler mit 4 Läufen/Tag
(`aicompany --mode live scheduler --interval 360 --max-runs 120`) oder cron. Leerläufe kosten nichts.

## Vorbereitung (Tag 0, ca. 1 Stunde)

1. Installation laut README, `aicompany demo` ansehen und im Control-Center einmal eine Freigabe genehmigen bzw. ablehnen, um die Bedienung kennenzulernen.
2. OpenAI-Konto: eigener Projektschlüssel, **Usage Limit ≈ 30 €**, Preise in `config/settings.toml` prüfen.
3. `aicompany selftest` → `aicompany preflight` → `aicompany --mode live serve`.
4. Optional schon jetzt: Domain und statischen Hoster auswählen (noch nichts kaufen; Käufe laufen später über Freigaben).

## Phase 1 – Recherche und Auswahl (Tag 1–5)

| Tag | System | Du |
|---|---|---|
| 1 | Research untersucht ≥ 5 Nischen mit Websuche; Strategy bewertet (0–100); Finance rechnet Szenarien; QA prüft Belege | Ereignisse beobachten; **Quellen im Research-Ergebnis stichprobenartig öffnen** (Dateien-Tab) |
| 2 | CEO wählt die Idee (oder fordert Nachrecherche an, max. 2×); Programmregeln prüfen die Auswahl | Auswahl und Scorecard lesen; bei Zweifel Research-Aufgabe per „Erneut versuchen“ wiederholen |
| 3–5 | Puffer für Nachrecherche und Überarbeitungen | – |

**Meilenstein M1**: Idee ausgewählt. **Abbruchkriterium**: Keine Idee erreicht die Mindestpunktzahl 55 → Suchfeld in
`settings.toml` (`company.goal`) schärfen und neu starten.

## Phase 2 – Produktentwicklung (Tag 6–12)

| System | Du |
|---|---|
| Product definiert das MVP (max. 5 must-Features), CEO prüft | MVP-Spec lesen |
| Builder baut eine statische App in `workspace/product/`, QA testet; Rückgaben bis max. 2× | `workspace/product/index.html` lokal im Browser öffnen und selbst ausprobieren |

**M2**: MVP gebaut und von QA bestätigt.

## Phase 3 – Marktvorbereitung (Tag 13–17)

| System | Du |
|---|---|
| Marketing: Positionierung, Landingpage-Texte, Hypothesen (z. B. „≥ 1 % Kaufinteresse“) | Texte auf Ehrlichkeit prüfen |
| Finance: Preis; Sales: Kanäle mit Rechtsgrundlage; Builder: Landingpage in `workspace/site/` | **Impressum und Datenschutzerklärung ausfüllen** (Platzhalter `[Vom Eigentümer auszufüllen]`) |
| QA: Compliance-Prüfung; Operations: Runbook + Freigabeantrag „Website veröffentlichen“ | Zahlungsweg einrichten (z. B. Payment-Link), Link in die Landingpage eintragen |

**M3**: Marktvorbereitung abgeschlossen.

## Phase 4 – Markttest (Tag 18–26)

| System | Du |
|---|---|
| Freigabeanträge: Website, Fachbeitrag, ggf. Mini-Anzeigentest (Budgetwirkung wird angezeigt) | **Freigaben entscheiden**; genehmigte Website: Release-Paket aus `data/live/releases/<ID>/` hochladen; bei manuellen Aktionen „Ausführung bestätigen“ inkl. tatsächlicher Kosten |
| Analytics: Messplan mit Mindeststichprobe; Marketing: Experimente | **Täglich echte Messwerte eintragen** (Tab „Kennzahlen“): `visitors`, `inquiries`, `sales`, `revenue_eur` |
| Tag 22: Zwischenauswertung (nur echte Daten, statistische Einordnung) | Empfehlungen lesen; unwirksame Maßnahmen stoppen |

**M4**: Markttest ausgewertet. Leitplanke: kein Werbebudget, bevor 300 organische Besucher gemessen sind (Bedingung des CEO im Demo-Lauf; im Live-Lauf entscheidet der CEO selbst).

## Phase 5 – Auswertung (Tag 27–30)

| System | Du |
|---|---|
| Analytics vergleicht Hypothesen mit Daten; Finance gleicht Prognose und Ist ab | – |
| CEO entscheidet: **Fortführen / Kurswechsel / Beenden**; Abschlussbericht | Bericht lesen (Tab „Ziele & Meilensteine“), Entscheidung bestätigen oder überstimmen |

**M5**: Abschlussentscheidung.

## Entscheidungsregeln für Tag 30 (Vorschlag)

| Ergebnis | Empfehlung |
|---|---|
| ≥ 1 zahlender Kunde und Conversion ≥ 1 % bei ≥ 300 Besuchern | Fortführen: Preis/Kanal optimieren, zweiten Zyklus starten |
| Interesse (Anfragen), aber keine Käufe | Kurswechsel: Preis, Angebot oder Zielgruppe ändern |
| < 100 Besucher | Test war nicht aussagekräftig → Reichweite verbessern, nicht das Produkt verwerfen |
| ≥ 300 Besucher, < 0,3 % Interesse | Beenden; nächste Idee aus der Scorecard testen |

## Budgetrahmen für die 30 Tage

| Posten | Plan |
|---|---|
| API | 1–5 € (Limit 30 €) |
| Domain/Hosting | 0–7 € |
| Werbung | 0–15 € (nur per Freigabe) |
| Reserve | Rest bis 100 € |
