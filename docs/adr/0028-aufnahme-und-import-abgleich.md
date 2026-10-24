# 0028: Aufnahme in bintafeln und Import-Abgleich

- Status: Angenommen
- Datum: 2026-10-24
- Ändert: die Festlegung „Kundenstamm nur als Snapshot“ (CLAUDE.md, ADR 0006, ADR 0025)

## Problem

Anträge kommen online herein und sollen direkt in bintafeln aufgenommen werden: Dubletten
erkennen, Daten abgleichen, Angehörige, Bescheid, Gültigkeit, Kundengruppe, Kundennummer,
Ausweisdruck. Gleichzeitig wird der Kundenstamm weiter aus dem Altsystem importiert, und jeder
Import ersetzte bisher alles, auch die Aufnahmen. Einen festen Stichtag für den Umstieg gibt es
nicht: An einem Tag werden alle Daten aus dem Altsystem geholt, ab dann gilt dieser Stand.

## Entscheidung

- **Aufnahme-Assistent** (`apps/antraege/aufnahme.py`, `views_aufnahme.py`) in sechs Schritten;
  der Zwischenstand liegt in der Sitzung, gespeichert wird erst am Ende in einer Transaktion.
  Neue Kunden bekommen die nächste freie Zahl als Kundennummer und den Merker
  `Haushalt.aufgenommen_am`.
- **Dublettensuche** über alle Personen: Namensähnlichkeit (auch vertauschte Vor-/Nachnamen,
  Umlaute, Tippfehler), Geburtsdatum (auch Tag und Monat vertauscht) und Anschrift; Punkte
  0–100, angezeigt ab 55.
- **Kapazität** einer Kundengruppe zählt Haushalte (ohne beendete); volle Gruppen werden nicht
  angeboten, die bisherige Gruppe eines bestehenden Kunden schon.
- **Gültigkeit** des Ausweises: Vorschlag aus den Kundeneinstellungen (Monate, bis Monatsende).
- **Import bleibt Vollaustausch, aber mit Abgleich:** Die Vorschau zeigt neue, entfallene und
  geänderte Haushalte mit den Unterschieden. Haushalte, die in bintafeln geändert oder
  aufgenommen wurden, können je Haushalt behalten werden; der Import lässt sie dann aus.
  Vorgabe ist „behalten“; „Für alle den Import übernehmen“ ersetzt alles.
- **Antragsnummern** sind fortlaufende Zahlen mit einstellbarem Startwert.

## Begründung

So kann die Tafel schon jetzt in bintafeln aufnehmen, ohne dass der nächste Import die Arbeit
stillschweigend löscht; wer bewusst den Stand des Altsystems will, wählt ihn je Haushalt oder
für alle. Der Vollaustausch bleibt einfach und nachvollziehbar.
