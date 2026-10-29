# 0038: Handbuch im Programm, nach Rechten gefiltert

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Mitarbeitende brauchen eine ausführliche Anleitung direkt im Programm. Wer am Einlass mit wenigen
Rechten arbeitet, soll nicht durch Kapitel über Mitarbeitende, Personal oder Einstellungen
blättern müssen.

## Entscheidung

- Seite „Hilfe“ für alle angemeldeten Konten. Kapitel sind Templates (`templates/hilfe/`), ihr
  Verzeichnis mit Teil und Rechten steht in `apps/core/hilfe.py`.
- Ein Kapitel erscheint, wenn das Konto mindestens eines seiner Rechte hat; Absätze innerhalb
  eines Kapitels richten sich mit `{% if "recht" in rechte %}` ebenfalls nach den Rechten.
- Alle sichtbaren Kapitel stehen auf einer Seite mit Inhaltsverzeichnis, damit die Suche des
  Browsers alles findet und man sie drucken kann.
- Neue oder geänderte Funktionen aktualisieren das Handbuch im selben PR; ein Test prüft, dass
  jedes Kapitel eine Vorlage hat und nur bekannte Rechte nennt.

## Begründung

Templates statt einer Markdown-Bibliothek: keine neue Abhängigkeit, Links und Bedingungen direkt
nutzbar. Die Bindung an Rechte nutzt dieselbe Grundlage wie Menü und Seiten (ADR 0033).

## Nachtrag: Bilder im Handbuch (2026-10)

- Kapitel können Bilder zeigen (`{% hilfe_bild "name" "Beschreibung" %}` aus
  `apps/core/templatetags/handbuch.py`), mit Pfeilen, Rahmen und Nummern in Tafel-Orange (`STANDARDFARBE`). Die
  Beschreibung unter dem Bild nennt die Schritte mit denselben Nummern (①, ②, …); ein Klick
  zeigt das Bild groß.
- Die Bilder macht niemand von Hand: `tests/e2e/test_hilfe_bilder*.py` (Werkzeug in
  `tests/e2e/hilfe_bilder.py`) spielt die Abläufe mit
  erfundenen Daten im Browser durch und nimmt sie auf (`BINTAFELN_HILFE_BILDER=1`). So kommen
  keine echten Personendaten hinein, und nach einer Änderung lassen sich alle Bilder mit einem
  Befehl erneuern. Ohne die Variable läuft derselbe Test in CI und schlägt fehl, wenn ein
  markiertes Element fehlt; `tests/test_hilfe.py` prüft, dass jedes benutzte Bild existiert und
  kein Bild übrig ist.
- Die Bilder zeigen die Standardfarbe und eine Muster-Tafel, nicht Farbe und Logo der jeweiligen
  Tafel; PNG mit 256 Farben, je Bild meist 20–70 KB.
