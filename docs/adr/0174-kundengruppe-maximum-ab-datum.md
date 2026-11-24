# ADR 0174: Maximum einer Kundengruppe ab einem Datum

## Problem

Die Vorschau der Wochenübersicht (ADR 0054, Nachtrag) rechnet geplante Umzüge ein. Wird eine
Kundengruppe dafür vergrößert, ließ sich das nur sofort eintragen – dann stimmte das Soll bis
zum Umzug nicht – oder erst am Tag selbst, dann fehlte es in der Vorschau.

## Entscheidung

- `Kundengruppe` bekommt zwei freiwillige Felder: `maximum_neu` und `maximum_ab`. Nur beide
  zusammen sind gültig (Formular).
- Bis zum Datum gilt überall weiter `maximum` (freie Plätze, Aufnahme, Statistik). Der tägliche
  Lauf (`verlegung.maxima_anwenden()` in `fristen_anwenden()`) macht das neue am Tag zum Maximum
  und leert die beiden Felder. Ein Datum von heute oder früher übernimmt das Formular sofort.
- Wer das Maximum an einem bestimmten Tag braucht, fragt `Kundengruppe.maximum_am(datum)` – so
  rechnet die Vorschau der Wochenübersicht das Soll je Tag. Listen zeigen `maximum_anzeige`
  („40 → 50 ab 01.12.2026“).

## Begründung

Eine geplante Änderung als zwei Felder an der Gruppe ist das Kleinste, was reicht: keine eigene
Tabelle, kein Verlauf. Weil der tägliche Lauf den Wert umträgt, muss kein anderer Programmteil
das Datum kennen; nur die Vorschau schaut voraus.
