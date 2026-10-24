# 0027: Kundenausweis frei gestalten

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0021 (PDF)

## Problem

Jede Tafel hat ihr eigenes Erscheinungsbild und will ihren Ausweis selbst gestalten: eigener
Ausweisname, andere Anordnung, Farben, Hintergrundbild, später eine Rückseite. Der Scanner am
Einlass muss den Ausweis aber immer lesen können.

## Entscheidung

- Eine **Ausweis-Vorlage** je Installation (`kunden.AusweisVorlage`) mit Elementen als JSON:
  Typ, Position und Größe in Millimetern von oben links, Schriftgröße, fett, Ausrichtung, Farbe,
  bei freiem Text der Text mit Platzhaltern. Dazu Ausweisname, Hintergrundbilder, Rückseite
  ein/aus und Seitenformat (A4 mit Schnittmarken oder Kartengröße).
- **Kundennummer und Barcode sind Pflicht** auf der Vorderseite und lassen sich nicht
  entfernen; der Barcode hat eine Mindestgröße (30 × 8 mm) und enthält nur die Kundennummer.
  Der Server prüft und begrenzt jedes Element (`apps/kunden/ausweis.py`), egal was der Browser
  schickt.
- Der **Gestalter** ist eine Seite für den Admin mit einem kleinen eigenen Skript
  (`static/js/ausweis_gestalter.js`, kein Framework): verschieben, Größe ändern, Pfeiltasten,
  Eigenschaften. Das PDF zeichnet die Elemente mit denselben Maßen.
- Ohne eigene Gestaltung gilt eine Standard-Vorlage, die dem bisherigen Ausweis entspricht.
- **Sammeldruck** aus der Kundenliste: ein PDF mit einem Ausweis je Seite für die aktuelle
  Auswahl, höchstens 500.

## Begründung

Millimeter von oben links sind für Menschen verständlich und gelten gleich im Browser und im
PDF. Pflicht-Elemente und Prüfung auf dem Server sichern, dass jeder Ausweis am Einlass
funktioniert, auch wenn jemand die Gestaltung verunglückt.
