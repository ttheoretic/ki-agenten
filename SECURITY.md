# Sicherheitsmodell

Grundsatz: **Prompts beschreiben Regeln, das Programm setzt sie durch.** Keine Sicherheitsfunktion hängt davon ab,
dass ein Modell sich an Anweisungen hält.

## Schichten

1. **Keine gefährlichen Werkzeuge.** Agenten bekommen höchstens die gehostete Websuche. Es gibt keine Shell, keinen
   Code-Interpreter, kein Computer-Use und keine Dateisystem-Werkzeuge. Dateien schreibt ausschließlich das Programm,
   nach Prüfung (`OpenAIAgentsBackend._build_agent`).
2. **Default-Deny-Aktionsklassen** (`config/security.toml`): `auto_allowed`, `approval_required`, `forbidden`.
   Unbekannte Aktionen sind verboten. Verbotene Anträge werden abgewiesen und als `security.violation` protokolliert.
3. **Sandbox** (`security.Sandbox`): nur relative Pfade innerhalb von `data/<modus>/workspace`, nur in den Ordnern des
   jeweiligen Agenten. `..`, absolute Pfade, `~`, Laufwerksbuchstaben und Symlinks werden abgelehnt. Es gelten Dateigrößen-,
   Dateianzahl- und Dateitypgrenzen. Die Konfiguration liegt außerhalb des Workspace und ist für Agenten unerreichbar.
4. **Generierter Code wird nicht ausgeführt**, nur statisch geprüft: keine externen Skripte/Ressourcen, kein Tracking,
   kein `eval`/`new Function`/`document.cookie`, keine Geheimnisse, keine unzulässigen Werbeaussagen, Pflichtseiten vorhanden.
5. **Freigaben** (`approvals.py`):
   - Parameter werden per Schema validiert (z. B. E-Mail-Empfänger, Beträge) und sind danach unveränderlich (SHA-256-Hash).
   - Die Genehmigung muss den Hash bestätigen, den der Mensch gesehen hat. Manipulierte Parameter in der DB werden erkannt.
   - Genehmigung ≠ Ausführung: Die Ausführung läuft separat, **genau einmal** (bedingtes UPDATE), und nur mit den gespeicherten Parametern.
   - Budgetprüfung bei Genehmigung; Ablaufdatum; mehr als 25 Empfänger gelten als Massenkommunikation (verboten).
   - Das System zahlt nie selbst. Zahlungen, Werbung, Verträge usw. enden als `manual_required` und werden vom Menschen
     ausgeführt und bestätigt. Tatsächliche Kosten über dem genehmigten Betrag erfordern einen neuen Antrag.
   - Ohne konfigurierten Anbieter werden Nachrichten nur in den lokalen Postausgang gelegt und **nicht** versendet.
     Websites werden als lokales Release-Paket exportiert. Das Ergebnis meldet `external_effect: false`.
6. **Steuerung**: `pause`, `stop_new`, `stop` liegen in der Datenbank. Sie blockieren neue Aufgaben und externe Aktionen
   auch in anderen Prozessen. `stop` bricht laufende Aufrufe kontrolliert ab; die Aufgaben gehen zurück auf `pending`.
7. **Geheimnisschutz** (`Redactor`): Werte aller Umgebungsvariablen mit KEY/TOKEN/SECRET/PASSWORD sowie typische
   Schlüsselmuster werden vor jeder Speicherung (Ereignisse, Dateien, Freigaben, Entscheidungen) und vor jeder
   Dateiansicht entfernt. Das Owner-Token wird ebenfalls maskiert. Tracing an den Anbieter ist standardmäßig deaktiviert.
8. **Policy-Fingerprint**: Änderungen an `security.toml` werden beim Start erkannt und als Ereignis gemeldet.
9. **Prompt-Injection**: Eingaben werden als Datenblock (`<<<DATEN … DATEN>>>`) übergeben, mit der Anweisung, darin
   enthaltene Befehle zu ignorieren. Entscheidend ist aber, dass ein manipuliertes Modell **nichts Externes ausführen
   kann**: Es kann höchstens Anträge stellen, die ein Mensch prüft.

## Control-Center / API

- Alle Endpunkte außer `/api/health` verlangen das **Owner-Token**: `Authorization: Bearer …`, für EventSource und
  Dateiansicht alternativ `?token=`. Der Vergleich erfolgt in konstanter Zeit.
- Das Token wird bei `init`/`serve` erzeugt (`data/<modus>/owner_token`, Rechte 0600) oder per `AICO_OWNER_TOKEN` gesetzt.
  Die Start-URL übergibt es im URL-Fragment (wird nicht an den Server gesendet). Die Oberfläche entfernt es aus der
  Adresszeile und hält es nur im `sessionStorage`.
- Der Server bindet standardmäßig nur an `127.0.0.1`. `TrustedHostMiddleware` schützt gegen DNS-Rebinding. Gesetzt sind
  CSP (`script-src 'self'`), `X-Frame-Options: DENY`, `nosniff` und `no-referrer`.
- Agentenausgaben werden in React als Text gerendert (kein `dangerouslySetInnerHTML`). Dateien liefert der Server als
  `text/plain` mit `Content-Security-Policy: sandbox` aus. Erzeugte HTML-Seiten werden also nie im Control-Center ausgeführt.
- Freigaben und Steuerungsaktionen werden im `audit_log` protokolliert (`GET /api/audit`).
- Ein Button-Klick kann keine Prüfung umgehen: Das Backend validiert Status, Ablauf, Hash, Richtlinie und Budget bei jeder Entscheidung.

## Nicht abgedeckt / Restrisiken

- Kein Mehrbenutzer-Rollenmodell: Ein Owner-Token berechtigt zu allem. Für den Betrieb außerhalb von localhost einen
  Reverse-Proxy mit TLS und zusätzlicher Authentifizierung vorschalten.
- Inhaltliche Richtigkeit (Recherche, Rechtstexte) kann das Programm nur begrenzt prüfen. Für Rechtliches haftet der Eigentümer.
- Gehostete Websuchen innerhalb **eines** Aufrufs lassen sich nicht einzeln deckeln, nur über `max_turns` und das Laufbudget.
