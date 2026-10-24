# 0023: Versionen nach Kalender

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0008

## Problem

Bisher holte `./betrieb update` den jeweils neuesten Stand von `main`. Es gab keine
Versionsnummer, an der Tafeln und Maintainer erkennen, welcher Stand installiert ist.

## Entscheidung

- Versionen heißen `JAHR.MONAT.NUMMER` (z. B. `2026.10.1`), die Nummer zählt je Monat ab 1.
  Monat ohne führende Null, damit die Nummern auch für gängige Werkzeuge gültige Versionen sind.
- Nach jedem Merge auf `main` legt der Workflow `version.yml` den nächsten Tag und ein
  GitHub-Release mit automatisch erzeugten Änderungsnotizen an.
- `./betrieb update` zeigt die letzten Versionen mit Nummern und nimmt ohne Eingabe nach drei
  Sekunden die neueste; `./betrieb update VERSION` bzw. `main` wählt direkt.
- **Zurück auf eine ältere Version** (Nachtrag Oktober 2026, vorher ausgeschlossen): nach
  Rückfrage und Sicherung setzt der noch laufende neuere Code die Datenbank mit Django-
  Migrationen rückwärts auf den Stand der älteren Version, erst danach wird diese gebaut. Neue
  Migrationen müssen deshalb umkehrbar sein (RunPython immer mit Rückweg, notfalls `noop`).
- `./betrieb update` schreibt die Version in die Datei `VERSION` (nicht im Repository). Admins
  sehen sie unten auf jeder Seite, `./betrieb status` zeigt sie ebenfalls.

## Begründung

Eine Kalenderversion sagt sofort, wie alt ein Stand ist, und passt zu einem Projekt ohne
geplante große Versionssprünge. Der automatische Tag vermeidet Handarbeit und Tippfehler.
