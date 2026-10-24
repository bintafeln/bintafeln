# 0031: Historie eines Haushalts

- Status: Angenommen
- Datum: 2026-10-24

## Problem

Das Büro soll sehen, was sich an einem Haushalt geändert hat: neu aufgenommen, Status,
Kundengruppe, Ausweis verlängert, Personen hinzugekommen oder entfallen (Fachkonzept). Im
Snapshot-Betrieb ersetzt jeder Import den Kundenstamm; Änderungen kommen außerdem aus der
Aufnahme von Anträgen und der Bearbeitung durch den Admin.

## Entscheidung

- `HaushaltEreignis` mit Kundennummer, Zeitpunkt, Quelle (Import, Aufnahme, Bearbeitung),
  lesbarem Text und wer es war. Eine Zeile je Änderung. Hängt an der Kundennummer und übersteht
  den Import.
- `apps/kunden/historie.py` vergleicht Schnappschüsse vor und nach einer Änderung (Status,
  Kundengruppe, Ausweis gültig bis, Personen nach Name und Geburtsdatum). Alle drei Wege nutzen
  denselben Vergleich; der Import vergleicht den ganzen Bestand vorher und nachher.
- Ein neu aufgenommener oder angelegter Haushalt bekommt eine Zeile („Aufgenommen mit Antrag …“,
  „Angelegt“, „Neu im Kundenstamm“), keine Einzelzeilen.
- Eigene Löschfrist (`historie_aufbewahren_jahre`, Vorgabe 3) in den Kundenstamm-Einstellungen.
  Löscht der Admin einen Haushalt, wird seine Historie mitgelöscht. Die Auskunft nach Art. 15
  enthält die Historie.

## Begründung

Ein Vergleich vorher/nachher an einer Stelle statt Signalen an jedem Modell: Er funktioniert
gleich für Import (Massenaustausch per `bulk_create`, ohne Signale) und Einzeländerungen und
hält nur fest, was fachlich zählt. Das Änderungsprotokoll (django-auditlog) bleibt für die
technische Nachvollziehbarkeit zuständig.
