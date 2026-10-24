# 0024: Online-Anträge in 29 Sprachen, Warteliste außerhalb

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0006, ADR 0021

## Problem

Menschen sollen sich online bei der Tafel anmelden oder ihre Berechtigung verlängern können,
in ihrer Sprache. Die Warteliste arbeitet die Tafel derzeit mit einem eigenen Programm ab.

## Entscheidung

- **Öffentliches Formular** unter `/antrag/`, ohne Anmeldung, in 29 Sprachen. Die Sprache kommt
  aus dem Browser und lässt sich oben umstellen; Arabisch, Persisch, Dari, Paschtu, Sorani und
  Urdu werden von rechts nach links gesetzt.
- Die **Übersetzungen liegen im Programm** (`apps/antraege/uebersetzungen/<code>.json`).
  Kein fremder Übersetzungsdienst: Was Antragstellende eingeben, verlässt den Server nicht.
  Die Tafel kann Einleitung und Bestätigungstext je Sprache selbst schreiben.
- Je Feld stellt die Tafel ein: nicht abfragen, freiwillig oder Pflicht. Vorgabe ist sparsam;
  Familienstand und Staatsangehörigkeit sind aus. Das Formular ist zunächst ausgeschaltet.
- **Bestätigung** auf dem Bildschirm und, wenn eine Adresse angegeben ist, per Mail in der
  gewählten Sprache. Ausgewählte Mitarbeitende erhalten eine Mail ohne persönliche Angaben.
- **Missbrauchsschutz** ohne fremde Dienste: ein für Menschen unsichtbares Feld, höchstens fünf
  Absendungen je Adresse und Stunde (gespeichert nur als Prüfsumme, nach einem Tag gelöscht),
  Nachweise nur als Foto oder PDF, höchstens fünf Dateien mit je 10 MB, verschlüsselt abgelegt.
- **Bearbeitung** durch Admin und Büro: Status, Anmerkungen, Papierkorb, Auskunft als PDF.
  Fristen: unbearbeitet nach N Tagen erledigt (Vorgabe aus), abgeschlossen nach 90 Tagen in
  den Papierkorb, nach weiteren 30 Tagen gelöscht, samt Nachweisen und Protokolleinträgen.
- Ein Antrag wird **nicht automatisch Kunde**: Solange der Kundenstamm aus dem Altsystem kommt,
  überträgt das Büro angenommene Anträge dorthin.
- Die **Warteliste** wird außerhalb von bintafeln abgearbeitet. bintafeln führt die Anträge in
  der Reihenfolge des Eingangs und exportiert sie als CSV.

## Begründung

Eigene Übersetzungen sind datenschutzfreundlich und funktionieren ohne Internetdienste. Die
Felder und Fristen sind einstellbar, damit jede Tafel nur erhebt, was sie braucht. Die
Warteliste bleibt vorerst im vorhandenen Programm, damit nichts doppelt gepflegt wird.
