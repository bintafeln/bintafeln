# 0011: Abholungen und Ausnahmen mit Aufbewahrungsfrist

- Status: Angenommen
- Datum: 2026-10-23
- Ergänzt: ADR 0006, ADR 0010

## Problem

Ursprünglich sollten einzelne Abholungen erst mit dem Modul Ausgabe kommen. Für die Arbeit am
Empfang und für Rückfragen („Wann war der Haushalt zuletzt da?“) braucht eine Tafel aber schon im
Snapshot-Betrieb die letzten Abholungen und die erteilten Ausnahmen. Abholungen zeigen, wer wann
bei der Tafel war. Das ist eine sensible Angabe, die nicht unbegrenzt gespeichert werden darf.

## Entscheidung

- Das Importformat erhält die optionalen Dateien `abholungen.csv` (Datum, Uhrzeit, Beitrag,
  Ausgabestelle, eingetragen von) und `ausnahmen.csv` (Datum, Begründung, eingetragen von). Sie
  werden wie alle Teile des Kundenstamms bei jedem Import vollständig ersetzt.
- Für beide gilt eine **Aufbewahrungsfrist** in Jahren, einstellbar je Tafel (1 bis 10, Vorgabe
  **3 Jahre**). Ältere Einträge werden nicht importiert (Warnung im Prüfbericht) und in bintafeln
  automatisch gelöscht. Das Löschen erzeugt keine Einträge im Änderungsprotokoll, damit die
  gelöschten Angaben dort nicht weiterleben.
- Vom Kundenkonto wird weiterhin nur der aktuelle **Kontostand** übernommen, keine einzelnen
  Buchungen.

## Begründung

Drei Jahre decken die üblichen Rückfragen und Auswertungen ab und entsprechen der regelmäßigen
Verjährungsfrist. Wer weniger braucht, stellt die Frist kürzer. Statistiken über längere Zeiträume
sollen später aus anonymen Zählwerten entstehen, nicht aus aufbewahrten Einzelabholungen.
Einzelne Kontobuchungen bringen im Snapshot-Betrieb keinen Nutzen, der ihre Speicherung
rechtfertigt.
