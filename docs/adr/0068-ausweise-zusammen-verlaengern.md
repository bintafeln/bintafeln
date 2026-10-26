# 0068: Ausweise zusammen verlängern

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Ausgabestellen prüfen die Bescheide ihrer Kunden und melden der Verwaltung, dass verlängert werden
kann. Die Verwaltung musste danach jeden Haushalt einzeln öffnen und das Datum ändern. Dazu kommt:
Ob verlängert werden darf, regelt jede Tafel anders, z. B. nur, wenn alle Personen im Haushalt
mindestens 60 Jahre alt oder schwerbehindert sind; die anderen pausieren ein Jahr.

## Entscheidung

- Jede `Nachricht` der Ausgabestellen (ADR 0062) hat ein **Anliegen** aus einer festen Liste
  (`apps/core/auswahl.py`). Das Fenster gibt es am Einlass jetzt auch bei eigenen Kunden; die
  Startseite zählt die offenen Nachrichten je Anliegen. Eine Notiz-Vorlage kann ein Anliegen
  „melden“: Der Knopf am Einlass speichert dann die Notiz und legt zugleich die Nachricht an
  (höchstens eine offene je Haushalt und Anliegen). So bleibt der gewohnte Knopf „Bescheide
  geprüft …“ der Weg der Ausgabestellen.
- Haushalte mit offener Nachricht „verlaengern“ stehen auf der Seite „Kunden → Ausweise
  verlängern“. `apps/kunden/verlaengerung.py` prüft jeden: Status, aktive Sperre und die
  Bedingungen aus `KundenEinstellungen` (Regel ohne / jede Person / mindestens eine Person;
  Mindestalter, Ja/Nein-Zusatzfelder, Einkommensarten). Ergebnis: verlängerbar, nicht verlängerbar
  oder „selbst prüfen“ (fehlendes Geburtsdatum).
- Mit einem Klick werden alle gewählten verlängert (ab bisherigem Ablauf, bei abgelaufenem Ausweis
  ab heute; Monate wählbar, Vorgabe wie bei der Aufnahme). Für nicht verlängerbare stellt die
  Tafel ein (`verlaengern_ablehnung`): Notiz an die Ausgabestelle mit fehlender Bedingung je
  Person und Pause (Vorgabe; Status bleibt, der Ausweis läuft ab), Status „pausiert“ mit Notiz,
  oder nur anzeigen. Die gemeldete Notiz wird gestrichen. Jede Änderung geht
  über Historie und Kundengruppen-Regel (ADR 0031, 0061) wie eine Bearbeitung; die Nachrichten
  sind danach erledigt.
- Vorgabe für neue Installationen: ohne Bedingung. Die Bedingungen stellt jede Tafel selbst ein.

Manche Tafeln kennen keinen Status „pausiert“: Der Ausweis läuft einfach ab, der Haushalt fällt
dann aus der Kundengruppe (ADR 0061), und nach der Pause meldet er sich über den Online-Antrag
neu an. Deshalb ist die Notiz an die Ausgabestelle die Vorgabe; eine automatische Wiederaufnahme
gibt es bewusst nicht. Kinder zählen bei „jede Person“ mit.

## Begründung

Die Prüfung läuft vorher für alle sichtbar, bevor etwas geändert wird; die Verwaltung entscheidet
je Haushalt mit einem Haken. Eine Pause setzt nur den Status und schreibt eine Notiz, statt eine
neue Automatik zu bauen; die Wiederaufnahme läuft wie bisher über einen Antrag.
