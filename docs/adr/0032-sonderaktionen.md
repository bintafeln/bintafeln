# 0032: Sonderaktionen

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Tafeln geben zeitweise zusätzlich etwas aus, z. B. Gutscheine vor Weihnachten oder Schulranzen.
Am Einlass muss sichtbar sein, wer schon etwas bekommen hat; das Büro braucht Zahlen. Das
Fachkonzept nennt Zeitraum, Auswahlmöglichkeiten und Teilnahmen.

## Entscheidung

- `Sonderaktion` mit Zeitraum, Menge je Haushalt (einmal, je Kind, je Person), optional nur für
  Haushalte mit Kindern, Hinweis für den Einlass. Wahlmöglichkeiten als `SonderaktionAuswahl`
  (zeilenweise gepflegt; beim Umbenennen bleiben vorhandene Einträge erhalten).
- `Teilnahme` an der **Kundennummer** (übersteht den Import wie Notizen, Dokumente, Historie),
  höchstens eine je Aktion und Haushalt (Datenbank-Bedingung). Die Menge wird beim Eintragen aus
  der Haushaltsgröße festgehalten.
- Eintragen am Einlass für Admin, Büro und Ausgabe, unabhängig von der Ampel: Ob jemand trotz
  Sperre etwas bekommt, entscheiden die Mitarbeitenden. Zurücknehmen nur am selben Tag.
- Pflege und Auswertung (mit CSV ohne Namen) für Admin und Büro.
- Teilnahmen werden nach der Frist für Abholungen gelöscht und stehen in der Auskunft.

## Begründung

Eine Teilnahme ist ein Ereignis wie eine Abholung und bekommt dieselbe Frist. Die Regeln liegen
als reine Funktionen in `apps/ausgabe/sonderaktionen.py`, damit sie ohne Oberfläche testbar sind.
