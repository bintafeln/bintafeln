# 0062: Nachrichten der Ausgabestellen zu fremden Kunden

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Ausgabestellen sehen nur ihre eigenen Kunden (ADR 0034). Kommt ein Kunde einer anderen
Ausgabestelle oder weiß die Ausgabestelle etwas über ihn (z. B. neuer Wohnort), konnte sie das
der Verwaltung nicht im Programm mitteilen, ohne Daten des Kunden zu sehen.

## Entscheidung

- Wo die Meldung „Kunde gehört nicht zu Ihrer Ausgabestelle“ erscheint (Einlass, exakte Suche in
  der Kundenliste), öffnet „✉ Nachricht an die Verwaltung“ ein Fenster mit einem Textfeld.
- Die Nachricht (`kunden.Nachricht`) hängt an der Kundennummer, mit Ausgabestelle und Absender.
  Wer schreibt, sieht weiterhin keine Daten des Kunden; die Ansicht prüft nur, dass es die
  Kundennummer gibt.
- Lesen und erledigen mit dem neuen Recht „Nachrichten der Ausgabestellen zu Kunden lesen“
  (Vorgabe Büro, per Datenmigration): eigene Seite mit Zahl im Menü, Hinweis auf der Startseite
  und Abschnitt auf der Haushaltsseite.
- Erledigte Nachrichten werden nach 90 Tagen gelöscht; die Nachrichten stehen in der Auskunft.

## Begründung

Der Datenschutz zwischen den Ausgabestellen bleibt gewahrt, und Hinweise gehen nicht auf Zetteln
verloren. Eine eigene, kurze Frist genügt, weil die Nachricht nach der Erledigung ihren Zweck
erfüllt hat.
