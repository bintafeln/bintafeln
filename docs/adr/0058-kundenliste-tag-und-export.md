# 0058: Kundenliste nach Ausgabetag und Export als CSV

- Status: Angenommen
- Datum: 2026-10-25

## Problem

An einer Ausgabestelle mit mehreren Ausgabetagen sehen Mitarbeitende alle Kunden der Stelle, brauchen
aber meist nur die ihres Tages. Außerdem wollen sie die Liste für die Arbeit vor Ort in Excel
haben.

## Entscheidung

- Neues Feld `Benutzer.ausgabetage` (Mehrfachauswahl Mo–So). Die Kundenliste filtert nach
  Ausgabetag (`Kundengruppe.wochentage`), angeboten werden nur Tage der eigenen Ausgabestellen.
  Vorbelegung: heute, wenn es ein eigener Tag ist, sonst der erste eigene; ohne eigene Tage heute,
  falls Ausgabe ist; sonst alle. Mit Suchtext ohne gewählten Tag gelten alle Tage.
- Export als CSV (Semikolon, UTF-8 mit BOM – Excel öffnet die Datei direkt) mit dem neuen Recht
  `kunden.exportieren` (Vorgabe: Büro und Ausgabe). Exportiert wird genau die gefilterte Liste der
  eigenen Ausgabestellen (`zugang.filtern`, ADR 0034).
- Spalten wählt der Admin in den Einstellungen des Kundenstamms (`export_felder`). Felder, die ein
  eigenes Recht brauchen (Kontakt, Kontostand, Art.-9-Zusatzfelder), bleiben ohne dieses Recht
  leer.
- Jeder exportierte Haushalt bekommt einen Eintrag im Zugriffsprotokoll (`Zugriff.export`).
- Zunächst CSV statt .xlsx, damit keine neue Abhängigkeit nötig ist.

## Begründung

Der Tagesfilter spart Suchen am Ausgabetag. Personendaten verlassen mit dem Export das System;
darum eigenes Recht, Spalten zentral festgelegt, Rechte je Feld und lückenloses Protokoll.
