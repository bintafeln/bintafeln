# 0054: Wochenübersicht der Ausgabestellen

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die bisherige „Ausgabestellen-Übersicht“ war ein eigenes Programm ohne Anmeldung. Sie holte ihre
Zahlen per Fernsteuerung aus einem Fremdsystem, erkannte Wochentag und Zentrale am Namen der
Kundengruppe und speicherte Zugangsdaten im Klartext.

## Entscheidung

- Zuschaltbares Modul `wochenuebersicht` (ADR 0049), Rechte `wochenuebersicht.sehen` und
  `wochenuebersicht.bearbeiten` (Vorgabe Büro).
- Zahlen direkt aus dem Kundenstamm: Soll = `Kundengruppe.maximum` (fehlt es, bleibt Soll leer
  statt Ist einzusetzen), Ist = aktive Haushalte, Erwachsene/Kinder über `Haushalt.groesse()`.
- Zusammengefasst wird über `Kundengruppe.ausgabestelle` und `Kundengruppe.wochentage`, nicht über
  Namen; eine Gruppe mit mehreren Tagen zählt an jedem davon. Reihenfolge einstellbar
  (`StellenReihenfolge`), sonst nach Name.
- Selbstabholer als eigene, gepflegte Liste (`Selbstabholer`); sie zählen nur zu „alle Personen“.
- Neu: auf Wunsch die Abholungen einer Kalenderwoche je Tag und Ausgabestelle.
- Druck nur als PDF (ADR 0021): Hochformat je Tag, Querformat im Aufbau der bisherigen Excel-Liste.

## Begründung

Die Daten liegen schon in bintafeln; ein Abgleich mit dem Fremdsystem ist überflüssig und war
fehleranfällig. Zuordnung über Felder statt Namen bleibt richtig, wenn Gruppen umbenannt werden.
