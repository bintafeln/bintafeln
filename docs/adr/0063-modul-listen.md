# 0063: Modul Listen

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Tafeln brauchen laufend Listen aus dem Kundenstamm: die Kundenliste einer Ausgabestelle, Kinder
unter 6 (Babynahrung), Kinder in einem Alter (Schulranzen, Weihnachten), Seniorinnen und Senioren,
Bürgergeld- oder Rentenhaushalte, Zählungen nach Staatsangehörigkeit oder Altersgruppe für
Berichte. Bisher entstanden sie per Export und Excel.

## Entscheidung

- Zuschaltbares Modul `listen` (ADR 0049) mit einem Katalog fertiger Listen
  (`apps/listen/katalog.py`): Grundlage Haushalte oder Personen, angebotene Filter mit
  Vorgaben, Spalten, Sortierung, Gliederung, „nur Summen“ und gegebenenfalls ein nötiges Recht.
- Spalten in `apps/listen/spalten.py` mit rohem Wert (sortier- und summierbar) und Recht
  (Stammdaten, Kontakt, Konto, Art. 9 bei Zusatzfeldern). Rechnen in Python
  (`abfrage.rechnen()`), damit abgeleitete Werte wie Alter und Altersgruppe genauso funktionieren.
- Grundmenge immer über `zugang.filtern()` (nur eigene Ausgabestellen). Listen, die Stammdaten
  zeigen oder danach filtern (Staatsangehörigkeit, Einkommensart), nur mit „Stammdaten sehen“.
- Auf der Seite: Filter, Spalten wählen, sortieren per Klick, gliedern nach jeder Spalte mit
  Anzahl und Summen. Jede Zeile hat ein Auswahlkästchen (Kopf: alle/keine); CSV (Excel, mit BOM)
  und PDF nehmen die Auswahl oder alles. Jeder Export schreibt das Zugriffsprotokoll.
- „Eigene Listen“ (`EigeneListe`) speichern nur die Einstellungen (Adresszeile), privat oder mit
  „Listen für alle speichern“ für alle.
- Rechte „Listen ansehen, drucken und exportieren“ (Vorgabe Büro und Ausgabe) und „Eigene Listen
  für alle speichern“ (Büro).

## Begründung

Ein Katalog mit wenigen, klaren Bausteinen deckt die meisten Wünsche ab, ohne für jede Liste
eigenen Code zu schreiben; neue Listen sind ein Eintrag im Katalog. Die Rechte der Kundendaten
gelten unverändert, Exporte bleiben nachvollziehbar.

## Nachtrag: Freigabe-Ziele mehrfach wählbar (2026-11-01)

Die Sichtbarkeit einer eigenen Liste (`EigeneListe.sichtbarkeit`) kann auf bestimmte Ziele
eingeschränkt werden: „Bestimmte Ausgabestellen“ (`ausgabestellen`) oder „Bestimmte Personen“
(`fuer_personen`). Beide sind `ManyToManyField`, es lassen sich also mehrere auf einmal wählen
(Mehrfachauswahl-Widget wie im Kern, `static/js/mehrfachauswahl.js`). `sichtbar_fuer()` prüft, ob
eine der gewählten Ausgabestellen zu den Stellen des Benutzers gehört bzw. ob der Benutzer unter
den gewählten Personen ist. Vorher war je Liste nur eine Ausgabestelle oder eine Person möglich;
die Migration übernimmt vorhandene Einzelwerte in die neuen Mehrfachfelder.
