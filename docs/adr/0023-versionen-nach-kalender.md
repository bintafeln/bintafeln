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
- `./betrieb update` installiert die neueste Version, `./betrieb update main` den
  Entwicklungsstand. Auf einen älteren Stand als den installierten geht das Werkzeug nie
  zurück, weil die Datenbank dann schon weiter migriert ist.
- `./betrieb update` schreibt die Version in die Datei `VERSION` (nicht im Repository). Admins
  sehen sie unten auf jeder Seite, `./betrieb status` zeigt sie ebenfalls.

## Begründung

Eine Kalenderversion sagt sofort, wie alt ein Stand ist, und passt zu einem Projekt ohne
geplante große Versionssprünge. Der automatische Tag vermeidet Handarbeit und Tippfehler.
