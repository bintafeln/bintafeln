# 0019: Gesetzliche Feiertage je Bundesland

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0014, ADR 0018

## Problem

Urlaubstage, Sollstunden und der Vorschlag für Vorauszahlungen zählten Montag bis Freitag,
Feiertage mussten von Hand berücksichtigt werden. Welche Tage gesetzliche Feiertage sind, hängt
vom Bundesland ab.

## Entscheidung

- bintafeln berechnet die gesetzlichen Feiertage aller 16 Bundesländer selbst
  (`apps/core/feiertage.py`, ohne zusätzliche Bibliothek): Ostern nach Gauß, die übrigen fest
  oder davon abgeleitet, Sonderregeln mit dem Jahr, ab dem sie gelten (z. B. Frauentag in
  Berlin ab 2019, Reformationstag in Norddeutschland ab 2018).
- Die Tafel wählt ihr Bundesland in den Einstellungen; im Code steht keines fest. Ohne Auswahl
  gibt es keine Feiertage (bisheriges Verhalten).
- Nur landesweite Feiertage. Feiertage einzelner Gemeinden (z. B. Mariä Himmelfahrt in Teilen
  Bayerns) werden wie bisher von Hand eingetragen.
- Feiertage zählen nicht als Arbeitstag (Urlaub, Krankheit, Sollstunden) und nicht als Abholtag
  im Vorschlag für Vorauszahlungen; der Vorschlag nennt ausgelassene Feiertage mit Namen.

## Begründung

Die Regeln sind überschaubar und ändern sich selten. Eine eigene Berechnung vermeidet eine
weitere Abhängigkeit, und Tests mit den bekannten Daten sichern sie ab.
