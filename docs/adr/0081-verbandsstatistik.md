# 0081: Verbandsstatistik

- Status: Angenommen
- Datum: 2026-10-28

## Problem

Der Tafel-Dachverband fragt jedes Jahr im August dieselben Zahlen ab, bezogen auf einen
Stichmonat (Juni) und mit Vergleich zum Vorjahresmonat: Kund:innen nach Alter, Geflüchtete aus der
Ukraine, Haushalte nach Einkommensart, Tafel-Aktive. Bisher musste das jedes Jahr von Hand oder im
Altprogramm zusammengesucht werden.

## Entscheidung

- Neue Seite „Auswertungen → Verbandsstatistik“ (`statistik:verband`, Recht `statistik.sehen`),
  Rechnung in `apps/statistik/verband.py`, als Seite, CSV (alle Fragen) und PDF.
- Gezählt werden Haushalte mit mindestens einer Abholung im Stichmonat (jeder einmal) und alle
  Personen dieser Haushalte; Alter am letzten Tag des Monats (unter 18, 18–62, ab 63). Ukraine nach
  Staatsangehörigkeit. Einkommensart, wie sie am Haushalt steht.
- Vergleich mit dem Vorjahresmonat in den Stufen −3 … +3 des Fragebogens (`stufe()`); liegen die
  Abholungen des Vorjahres vor der Löschfrist, gibt es keinen Vergleich (Hinweis statt Zahl).
- Tafel-Aktive aus den aktiven Konten (ohne Konten der Ausgabestellen), Alter und Anrede aus den
  Stammdaten; „selbst Kund:in“ über gleichen Namen und gleiches Geburtsdatum im Kundenstamm.
- Wie die übrige Statistik auf Wunsch je Ausgabestelle; Mitarbeitende einer Ausgabestelle sehen
  nur deren Zahlen.

## Begründung

Die Fragen ändern sich selten; eine feste Auswertung aus den vorhandenen Daten spart jedes Jahr
Arbeit. bintafeln historisiert die Haushaltszusammensetzung nicht; das steht als Hinweis auf der
Seite, wie schon im Altprogramm. Nur Summen, keine Personendaten.
