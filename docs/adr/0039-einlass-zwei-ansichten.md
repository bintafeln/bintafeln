# 0039: Einlass in zwei Ansichten: Suche oder Kunde

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Am Einlass stand das Feld zum Scannen auch dann oben, wenn ein Kunde angezeigt wurde. Der Knopf
zum Eintragen lag weiter unten zwischen Hinweisen, und nach dem Eintragen blieb der Kunde stehen.
Das war unübersichtlich: Man sah nicht sofort, was zu tun ist und wann ein Kunde fertig ist.

## Entscheidung

- Der Einlass hat zwei Ansichten, die per HTMX im Bereich `#einlass` getauscht werden
  (`templates/ausgabe/_einlass.html`):
  - **Suche**: Feld zum Scannen, Ausgabestelle, Meldungen („nicht gefunden“, Bestätigung).
  - **Kunde**: kein Suchfeld. Oben links die Kundennummer, oben rechts Beitrag, „Gezahlt“ und die
    Knöpfe **„Abholung eintragen“** (grün) und **„Abbrechen“** (zurück zur Suche, nichts
    eingetragen; ohne Abholung heißt er „Zur Suche“). Darunter Ampel, Angaben, Notizen.
- Nach dem Eintragen einer Abholung erscheint immer wieder die Suche, mit Bestätigung und Link
  zurück zum Kunden (für eine Korrektur). Andere Aktionen (Zahlung, Ausnahme, Sonderaktion,
  Notiz, Rücknahme) bleiben beim Kunden.
- Das Kamera-Skript richtet Felder auch nach einem HTMX-Austausch ein.

## Begründung

Eine Ansicht je Arbeitsschritt macht klar, was gerade dran ist. Die Rückkehr zur Suche nach dem
Eintragen spart einen Klick je Kunde und verhindert, dass versehentlich der falsche Kunde offen
bleibt. Die Knöpfe stehen immer an derselben Stelle.
