# 0005: Änderungsprotokoll mit django-auditlog

- Status: Angenommen
- Datum: 2026-10-23

## Problem

Bei Kundendaten muss nachvollziehbar sein, wer wann welchen Datensatz geändert hat.

## Entscheidung

Das Änderungsprotokoll nutzt **django-auditlog**. Jedes Modell mit Personen- oder Stammdaten wird
mit `auditlog.register(...)` angemeldet. Protokolliert werden Zeitpunkt, handelnde Person, Art der
Änderung und die Felder vorher/nachher. Passwörter und andere Geheimnisse werden mit
`exclude_fields` ausgenommen. Admins sehen das Protokoll unter „Protokoll“.

## Begründung

- django-auditlog ist etabliert und gepflegt, eine eigene Lösung wäre mehr Code ohne Mehrwert.
- Es speichert nur die Änderungen in einer Tabelle, nicht vollständige Kopien jedes Datensatzes.

## Folgen

- Das Protokoll enthält selbst personenbezogene Daten. Es braucht eine eigene Aufbewahrungsfrist
  mit automatischer Löschung (noch offen).
- Der vollständige Austausch des Kundenstamms beim Import (ADR 0006) würde das Protokoll mit
  einem Eintrag je Datensatz füllen. Wie der Import protokolliert wird, ist beim Modul
  Kundenstamm zu entscheiden.
