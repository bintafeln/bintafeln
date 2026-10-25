# 0046: Mitglieder des Trägervereins

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die meisten Tafeln sind Vereine. Sie führen Mitglieder mit Nummer, Eintritt, Austritt und
Beitrag und müssen sehen, wer seinen Beitrag noch nicht gezahlt hat. Beiträge sind zugleich
Zuwendungen, die bestätigt werden können.

## Entscheidung

- Neue App `mitglieder`: `Mitglied` gehört 1:1 zu einer `Adresse` (ADR 0044), mit Nummer
  (fortlaufend vorgeschlagen, `MitgliederEinstellungen`), Art, Eintritt, Austritt mit Grund,
  Jahresbeitrag, Zahlweise und Zahlungsart (alles Auswahllisten in `apps/core/auswahl.py`) und
  optional dem Konto, falls das Mitglied zugleich mitarbeitet.
- **Beitragszahlungen sind Spenden mit `mitgliedsbeitrag=True`** (ADR 0045). Es gibt keine
  eigene Zahlungstabelle: Zahlungen erscheinen in den Spenden, in der Auskunft und lassen sich
  bestätigen. Soll je Jahr = Jahresbeitrag, wahlweise anteilig nach angefangenen Monaten der
  Mitgliedschaft; offen = Soll minus gezahlte Mitgliedsbeiträge des Jahres.
- Adressen mit Mitgliedschaft sind nicht löschbar; die Mitgliedschaft lässt sich löschen,
  Adresse und Zahlungen bleiben.
- Rechte `mitglieder.sehen`, `mitglieder.bearbeiten` (Büro beide), `einstellungen.mitglieder`.
- **Beiträge sind abschaltbar** (`MitgliederEinstellungen.beitraege`, Vorgabe aus): Die meisten
  Tafeln erheben keine Mitgliedsbeiträge. Ist sie aus, zeigen Formular, Liste, Mitgliedsseite,
  CSV, Spendenformular (Häkchen „Mitgliedsbeitrag“, außer an einer Spende, die es schon trägt),
  Serienbriefe (Platzhalter, Filter) und Auskunft (Jahresbeitrag 0) nichts zu Beiträgen.
  Gespeicherte Werte bleiben unverändert. Die Migration schaltet sie ein, wenn schon Beiträge
  erfasst sind (Jahresbeitrag oder Vorgabe über 0, Spenden als Mitgliedsbeitrag).
- SEPA-Lastschriften folgen später (eigener Plan).

## Begründung

Ein Datensatz je Zahlung an einer Stelle verhindert Abweichungen zwischen Beitragsliste und
Spendenbuchhaltung. Die einfache Soll-Rechnung reicht für die üblichen Jahresbeiträge; wer
monatlich zahlt, zahlt mehrere Teilbeträge, die sich zum Jahr summieren.
