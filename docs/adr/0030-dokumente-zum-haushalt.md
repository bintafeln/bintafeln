# 0030: Dokumente zum Haushalt

- Status: Angenommen
- Datum: 2026-10-24

## Problem

Tafeln brauchen Bescheide, Erklärungen und Einwilligungen eines Haushalts griffbereit. Das sind
besonders schützenswerte Daten, die nicht länger als nötig aufbewahrt werden dürfen. Der
Kundenstamm wird bei jedem Import ersetzt; die Dokumente entstehen aber in bintafeln und dürfen
dabei nicht verloren gehen.

## Entscheidung

- Modell `HaushaltDokument` hängt an der **Kundennummer** (wie Notizen, ADR 0026), nicht am
  Datensatz. Ein Import lässt die Dokumente unberührt.
- Dateien liegen verschlüsselt unter `MEDIA_ROOT/privat/kunden-dokumente/` über
  `apps.core.privatdateien` (ADR 0017), ausgeliefert nur an Admin und Büro. Jeder Abruf schreibt
  einen `Zugriff` und einen Eintrag „Zugriff“ im Änderungsprotokoll.
- Jede `Dokumentart` hat eine **Aufbewahrungsfrist in Monaten**. Gezählt wird ab dem
  Dokumentdatum, ohne Datum ab dem Hochladen. `fristen_anwenden()` löscht abgelaufene Dokumente
  samt Datei. Die Frist wird bei jedem Lauf aus der Dokumentart berechnet, eine geänderte Frist
  gilt also auch für schon gespeicherte Dokumente.
- Verschwindet eine Kundennummer aus dem Import, bleiben ihre Dokumente bis zum Ende der Frist
  (Fachkonzept). Löscht der Admin einen Haushalt ausdrücklich, werden sie mitgelöscht.
- Die Auskunft nach Art. 15 nennt die Dokumente mit Titel, Art, Datum und Löschtag.

## Begründung

Gleiches Muster wie Notizen und Mitarbeiter-Dokumente: bekannt, getestet, ohne neue Abhängigkeit.
Eine Frist je Dokumentart statt je Dokument hält die Pflege einfach und sorgt dafür, dass nichts
ohne Löschtag gespeichert wird.
