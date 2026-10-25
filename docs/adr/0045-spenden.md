# 0045: Spenden und Zuwendungsbestätigungen

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Tafeln leben von Geld- und Sachspenden und müssen Spendern Zuwendungsbestätigungen nach den
amtlichen Mustern ausstellen. Jede Spende darf nur einmal bestätigt werden, die Bestätigungen
müssen nachvollziehbar nummeriert sein, und die Angaben zur Steuerbegünstigung müssen stimmen.

## Entscheidung

- Neue App `spenden` mit `Spende` (Geld oder Sache, an einer `Adresse` aus ADR 0044),
  `Zuwendungsbestaetigung` (fortlaufende Nummer, Art Einzel-/Sammel-/Sachbestätigung, Betrag,
  Storno) und `SpendenEinstellungen` (Körperschaft, Zwecke, Finanzamt, Steuernummer, Bescheid,
  Unterschrift, nächste Nummer).
- Mehrere unbestätigte Geldspenden eines Spenders in einem Jahr ergeben eine Sammelbestätigung
  mit Anlage, eine einzelne eine Einzelbestätigung; Sachspenden werden einzeln bestätigt und
  brauchen einen Wert. Ausstellen sperrt die Zeilen (`select_for_update`) und verknüpft die
  Spenden; die Nummer wird unter Sperre vergeben.
- Das PDF entsteht jedes Mal neu aus den gespeicherten Daten (kein Speichern von Dateien).
  Storno lässt die Nummer bestehen, das PDF zeigt „STORNIERT“, die Spenden sind wieder frei.
- Bestätigte Spenden sind nicht änderbar oder löschbar; Adressen mit Spenden oder
  Bestätigungen nicht löschbar (Aufbewahrungspflicht). Ohne vollständige Angaben in den
  Einstellungen wird keine Bestätigung ausgestellt.
- Die Texte folgen den amtlichen Mustern (BMF zu § 10b EStG). Ob sie zur jeweiligen Tafel passen,
  prüft die Tafel bzw. ihre Steuerberatung; deshalb sind Zwecke und Grundlage wörtlich einstellbar.
- Rechte `spenden.sehen`, `.erfassen`, `.bestaetigen` (Büro alle drei) und
  `einstellungen.spenden` (nur Admin).

## Begründung

Die Verknüpfung Spende → Bestätigung verhindert doppelte Bestätigungen ohne zusätzliche Listen.
PDFs aus Daten statt gespeicherter Dateien halten die Datenhaltung schlank und stimmen immer mit
dem Bestand überein; das amtliche Muster verlangt keine Archivierung als Datei.
