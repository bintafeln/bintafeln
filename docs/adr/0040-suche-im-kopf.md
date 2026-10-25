# 0040: Suche im Seitenkopf mit Kürzeln

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Wer einen Kunden, eine Notiz oder eine Anmerkung sucht, musste erst die passende Liste öffnen.
Notizen und Anmerkungen ließen sich gar nicht durchsuchen.

## Entscheidung

- Auf jeder Seite (angemeldet) steht im Seitenkopf ein Suchfeld. Ab 3 Zeichen holt es per HTMX
  die Treffer (`/suche/`, `apps/core/suche.py`) und zeigt sie darunter, je Bereich höchstens 8;
  Enter öffnet die Ergebnisseite (je Bereich bis 50).
- Ohne Kürzel: Kunden (Vor- und Nachname, Kundennummer, Abholberechtigte), Anträge,
  Mitarbeitende. Ein Kürzel mit Leerzeichen sucht nur in einem Bereich: `k` Kunden, `n` Notizen,
  `a` Anmerkungen (Haushalt und Antrag), `s` Anschrift, `t` Telefon/E-Mail, `d` Dokumente,
  `an` Anträge, `m` Mitarbeitende, `h` Handbuch. `?` zeigt die erlaubten Kürzel.
- Jeder Bereich hängt an Rechten (ADR 0033), Kunden und alles an der Kundennummer an der
  Zuordnung zu Ausgabestellen (ADR 0034). Ohne Recht „Haushalt ansehen“ führt ein Kundentreffer
  zum Einlass.
- Gesucht wird mit `icontains` in der Datenbank; Suchbegriffe werden nicht gespeichert.

## Begründung

Ein Feld für alles ist schneller als Menüwege. Kurze Kürzel sind schnell getippt und leicht zu
merken; ohne Kürzel bleibt die Suche auf Namen beschränkt, damit die Liste übersichtlich bleibt.
Für die Datenmengen einer Tafel reicht die einfache Suche ohne eigenen Suchindex.
