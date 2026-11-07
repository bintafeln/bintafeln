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
- **Bestätigung** auf dem Bildschirm und, wenn eine Adresse angegeben ist, per Mail auf Deutsch
  und darunter in der Sprache zur angegebenen Staatsangehörigkeit (ohne passende Sprache: der
  gewählten), damit auch Angehörige oder Beratungsstellen sie lesen können. Die Antragsnummer
  zeigen weder Seite noch Mail, damit niemand sie als Platz in einer Reihenfolge versteht. Ausgewählte Mitarbeitende erhalten eine Mail ohne persönliche Angaben.
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

## Nachtrag: eigene HTML-Texte und Farbe der Tafel

Tafeln wollen Formular, Bestätigungsseite und Antwortmail so gestalten wie ihre Webseite.
Überschrift, Einleitung, Seite nach dem Absenden und Antwortmail sind deshalb je Sprache als
HTML einstellbar, dazu optional eigenes CSS für das Formular. Das HTML wird vor jeder Anzeige
mit `nh3` auf eine feste Liste erlaubter Elemente, Attribute und CSS-Angaben gefiltert
(`apps/core/html.py`); Skripte, Ereignis-Attribute und `javascript:`-Links fallen weg. So kann
auch ein missbrauchtes Admin-Konto über diese Texte keine Besucher angreifen. Werte in
Platzhaltern (z. B. der Name aus dem Antrag) werden maskiert. Die Antwortmail geht als HTML mit
Klartextfassung hinaus. Die Farbe der Tafel (`TafelEinstellungen.farbe`, voreingestellt
Tafel-Orange) gilt für die ganze Anwendung; hellere und dunklere Töne sowie die Schriftfarbe
auf der Farbe werden daraus berechnet (`apps/core/farben.py`).

## Nachtrag: „neu“ nur für einen einstellbaren Zeitraum

`AntragEinstellungen.neu_nach_tagen` (Vorgabe 0 = aus) legt fest, wie lange ein Antrag ab Eingang
als Status `neu` gilt. `fristen_anwenden()` setzt einen noch unbearbeiteten Antrag danach
selbsttätig von `neu` auf `in_bearbeitung` – ein reiner Statuswechsel, es wird nichts gelöscht.
Das ist bewusst getrennt von `erledigt_nach_tagen`: Steht dort 0, wird auch `in_bearbeitung` nie
automatisch erledigt oder weggeräumt. Als Zielstatus dient das vorhandene `in_bearbeitung` und
nicht ein eigener Status „wartend“, um keine Verwechslung mit dem `Wartestand` der Warteliste
(ADR 0051) zu erzeugen.

## Nachtrag: Löschen (in den Papierkorb) gehört zum Bearbeiten

Der Löschen-Knopf 🗑 in der Antragsliste legt den Antrag in den gemeinsamen Papierkorb (ADR 0073,
wiederherstellbar) und gehört damit zum Bearbeiten: Er ist jetzt an `antraege.bearbeiten` gebunden
(so wie es die Beschreibung dieses Rechts – „… Papierkorb“ – schon sagt) und steht dadurch immer bei
den anderen Zeilen-Knöpfen (ansehen, bearbeiten, Anmerkung), statt erst mit dem stärkeren Recht
`antraege.loeschen` zu erscheinen. Das Wiederherstellen aus dem Papierkorb bleibt `antraege.loeschen`
vorbehalten.
