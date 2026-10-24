# 0036: Statistik mit Diagrammen

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die Tafel braucht Zahlen für Vorstand, Förderer und Planung: Abholungen gesamt und je
Ausgabestelle, wer erreicht wird, Auslastung, Einnahmen. Die Oberfläche kommt ohne
JavaScript-Framework und ohne fremde Server aus.

## Entscheidung

- Eigene App `statistik` mit dem Recht `statistik.sehen` (Vorgabe Admin, Büro).
- Abfragen als reine Funktionen in `auswertung.py`; nur Summen, keine Personendaten. Zeitraum frei
  wählbar; die Feinheit der Verläufe richtet sich nach der Länge (Tag, Woche, Monat).
- Diagramme werden auf dem Server als SVG gezeichnet (`diagramme.py`): eine Achse, dezente
  Hilfslinien, Werte per Tooltip, Legende bei mehreren Reihen, feste und auf Farbsehschwäche
  geprüfte Farbreihenfolge (höchstens acht Reihen, darüber „Andere“). Jeder Abschnitt hat
  zusätzlich eine Tabelle und einen CSV-Export.
- Wer einer Ausgabestelle zugeordnet ist (ADR 0034), sieht nur deren Zahlen.

## Begründung

SVG vom Server braucht keine Bibliothek, funktioniert offline, lässt sich drucken und später in
PDFs übernehmen. Tabellen und CSV machen die Zahlen ohne Diagramm zugänglich (Barrierefreiheit,
Weiterverarbeitung).
