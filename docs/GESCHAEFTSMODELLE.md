# Welche Geschäftsmodelle kann ein KI-Team (fast) allein betreiben?

Stand: Oktober 2026. Diese Einschätzung ist auch als Leitfaden in `config/business_models.toml` hinterlegt.
Research- und Strategy-Agent bekommen sie bei jeder Recherche und Bewertung mit.

## Die Kernfrage: Wo braucht es zwingend einen Menschen?

„Komplett allein“ scheitert bei jedem Modell an denselben Stellen:

- **Identität und Recht:** Konten bei Zahlungsanbietern und Hostern verlangen eine echte Person (Identitätsprüfung, Bankkonto). Dazu kommen Gewerbeanmeldung, Steuern und das Impressum.
- **Haftung:** Verträge, Rechtstexte und Datenschutzverantwortung liegen immer bei dir.
- **Vertrauen im Verkauf:** Kunden, die vor dem Kauf ein Gespräch, eine Vorführung oder einen Vertrag wollen.

Ein Geschäftsmodell eignet sich deshalb, wenn nach der einmaligen Einrichtung **keine laufenden menschlichen
Kontaktpunkte** nötig sind. Der Kunde findet das Angebot selbst, kauft per Kreditkarte, bekommt sofort Zugang und
braucht kaum Hilfe.

## Bewertung

| Modell | Autonomie | Warum |
|---|---|---|
| **Kleine Web-Tools zum Selbstbedienen** (Rechner, Generatoren, Konverter) | hoch | Statisch oder einfache Web-App, Kauf ohne Gespräch, kaum Support. Das Software-Team kann sie vollständig bauen und testen. |
| **Entwickler-Tools und APIs** | hoch | Technische Kunden kaufen per Kreditkarte und lesen Doku statt anzurufen. Mehrere Solo-Produkte dieser Art werden als profitabel genannt ([Superframeworks](https://superframeworks.com/articles/micro-saas-ideas-solo-developers), [BigIdeasDB](https://bigideasdb.com/simple-saas-ideas-for-solo-developers-2026)); die Umsatzzahlen dort sind Selbstauskünfte. Nachteil: Ausfälle kosten Kunden. |
| **Digitale Vorlagen und Arbeitshilfen** | hoch | Einmal erstellt, beliebig oft verkauft. Etsy erlaubt KI-erstellte digitale Produkte, verlangt aber eine Kennzeichnung je Angebot ([selfemployed.com](https://www.selfemployed.com/news/etsy-seller-ai-disclosure-fees-2026/), [Nightjar](https://nightjar.so/help-desk/do-i-need-to-disclose-that-my-product-images-are-ai-generated-on-etsy-or-shopify)). Ein eigener Shop umgeht Marktplatzregeln. |
| **Automatisierte Daten- und Berichtsdienste** | mittel–hoch | Abo-Modell und gut automatisierbar. Die Nutzungsbedingungen der Datenquellen müssen aber geprüft werden, und Fehler kosten Vertrauen. |
| **Ratgeber- und Vergleichsseiten mit Affiliate** | mittel | Google stuft massenhaft erzeugte Seiten ohne Mehrwert als „Scaled Content Abuse“ ab, unabhängig davon, ob Menschen oder KI sie schreiben ([ppc.land](https://ppc.land/scaled-content-abuse/)). Einnahmen kommen erst nach Monaten. |
| **E-Books (Amazon KDP)** | mittel–niedrig | KI-Angabe beim Upload ist Pflicht. Berichtet wird ein Limit von 3 neuen Titeln pro Tag ([Authors Guild](https://authorsguild.org/news/amazon-adds-to-kdp-generative-ai-policy-caps-daily-self-publishing-uploads/), [ScribeCount](https://scribecount.com/author-resource/protecting-books/kdp-ai-content-policy-the-compliance-guide)). Die Preise sind niedrig. |
| **Dienstleistungen auf Auftrag** (Agentur) | niedrig | Jeder Kunde will Abstimmung, Rückfragen und Reklamationen. Das skaliert nur mit Menschen. |
| **Komplexe Branchen-Software** (z. B. für Industriewerkstätten) | niedrig | Kunden wollen Vorführungen, Integrationen, Verträge und Support. Die Software zu bauen ist machbar, der Verkauf nicht ohne Menschen. |

Hinweis zu den Quellen: Die meisten Angaben stammen aus Fach- und Branchenblogs, nicht direkt aus den Richtlinien
der Plattformen. Vor einem Start bitte die aktuellen Regeln bei Etsy, Amazon KDP und Google Search Central prüfen.

## Konkrete Beispiele, die gut passen

1. **Angebots- und Stundensatzrechner für Handwerksbetriebe.** Web-Tool mit Vorlagenpaket, Einmalkauf 19–49 €.
   Das ist die Idee aus dem Dry-Run.
2. **Webhook-Tester oder Cron-Job-Überwachung für Entwickler.** Kleine API mit Dashboard, Abo 5–15 €/Monat.
   Kunden finden sie über Suche und Entwicklerforen.
3. **Generator für rechtssichere Formulare und Checklisten** in einer engen Nische, z. B. Übergabeprotokolle für
   Ferienwohnungen. Statische Vorlagen plus Online-Ausfüllhilfe. Die Rechtstexte müssen vorher geprüft werden.
4. **Preisbeobachtungs-Report** für eine Produktkategorie aus öffentlich zugänglichen, lizenzierbaren Daten.
   Wöchentliche E-Mail im Abo.
5. **Rechner und Konverter für eine Fachgruppe**, z. B. Materialbedarf für Fliesenleger oder Dosierungen in der
   Gartenpflege. Ein Basis-Tool ist kostenlos (Reichweite), Pro-Funktionen sind kostenpflichtig.

Gemeinsam ist allen: enge Zielgruppe mit konkretem, wiederkehrendem Problem, Kauf ohne Gespräch, wenig Support und
keine personenbezogenen Kundendaten im Kern. Das sind genau die Kriterien, nach denen das Team bewertet.

## Was trotzdem bei dir bleibt

Bei allen Modellen machst du einmalig: Konten (Hosting, Zahlungsanbieter, Domain), Gewerbe und Steuern, Impressum
und Datenschutz. Laufend bleiben die Freigaben, die über deinen Autopilot-Regeln liegen. Mit den geplanten Anbindungen
(Hosting-Upload, Verkaufs- und Besucherzahlen automatisch) sinkt der laufende Aufwand auf wenige Minuten pro Woche.
