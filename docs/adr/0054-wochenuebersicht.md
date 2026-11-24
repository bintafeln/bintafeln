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

## Nachtrag (2026-11-24): Vorschau auf kommende Wochen

Wichtiger als die Vergangenheit ist, wie es in den nächsten Wochen aussieht – etwa wenn eine
Ausgabestelle schließt und ihre Kunden schon auf andere verteilt sind. Die Kalenderwoche lässt
sich deshalb bis vier Wochen voraus wählen (`auswertung.uebersicht(..., vorschau=Montag)`). Jeder
Tag wird auf sein Datum gerechnet: geplante Umzüge (`GeplanterWechsel`, ADR 0118) zählen ab ihrem
Stichtag in der neuen Kundengruppe, eine Ausgabestelle mit `schliesst_am` fällt danach weg,
Schließzeiten (ADR 0144) stehen als „geschlossen“ und zählen nicht in die Summe, das Alter gilt am
Tag. Nicht eingerechnet wird, was niemand weiß (Neuaufnahmen, Abgänge) und was meist nicht
eintritt (ablaufende Ausweise – sie werden nur gezählt). Die Vorschau speichert nichts; sie liest
nur, was ohnehin geplant ist.
