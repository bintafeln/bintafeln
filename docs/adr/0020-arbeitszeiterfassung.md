# 0020: Arbeitszeiterfassung im Browser

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0018

## Problem

Das Stundenkonto der Festangestellten wurde mit von Hand eingetragenen Stunden geführt. Das ist
aufwendig und fehleranfällig. Arbeitgeber müssen die Arbeitszeit außerdem erfassen.

## Entscheidung

- Wer stempeln darf, stempelt unter „Meine Arbeitszeit“ im Browser **Kommen** und **Gehen**.
  Das geht am eigenen Handy oder an einem gemeinsamen Gerät nach Anmeldung. Ein eigenes
  Terminal oder eine eigene App gibt es nicht.
- Stempeln dürfen fest Angestellte. Ehrenamtliche nur, wenn es unter „Personal → Arbeitszeit
  einstellen“ eingeschaltet ist; ihre Zeiten sind dann Einsatzzeiten ohne Stundenkonto.
- Jeder Tag zählt nach Pausenabzug: Fehlt die Pause nach § 4 ArbZG (mehr als 6 Stunden:
  30 Minuten, mehr als 9: 45 Minuten), wird der fehlende Rest abgezogen. Als Pause gilt die
  Zeit zwischen Gehen und erneutem Kommen. Der Abzug lässt sich abschalten.
- Ein offenes Kommen, das älter als eine einstellbare Grenze ist (Vorgabe 14 Stunden), gilt als
  **vergessenes Gehen**. Es zählt nicht, das nächste Kommen ist trotzdem möglich, und das
  Personal sieht es zum Nachtragen.
- Korrekturen macht nur das Personal (Admin oder Rolle Personal), mit Pflicht-Begründung. Die
  Buchung trägt „korrigiert von“, jede Änderung steht im Änderungsprotokoll. Überschneidungen
  werden abgewiesen.
- Die gestempelten Stunden fließen als eigene Spalte ins Stundenkonto. Von Hand nachgetragene
  Stunden bleiben für Ausnahmen (Dienstreise, Ausgleich).
- Die Löschfrist für Personaldaten (ADR 0017) umfasst auch die Zeitbuchungen.

## Begründung

Der Browser ist schon da und mobilfreundlich; ein eigenes Gerät müsste jede Tafel beschaffen und
warten. Der automatische Pausenabzug hält das Stundenkonto gesetzeskonform, ohne dass jede
Pause gestempelt werden muss. Korrekturen nur durch das Personal und mit Begründung machen die
Erfassung nachvollziehbar.
