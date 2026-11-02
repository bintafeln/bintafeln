# 0006: Kundenstamm als Snapshot mit Vollaustausch

- Status: Angenommen
- Datum: 2026-10-23

## Problem

Tafeln führen ihre Kundendaten heute in einem Altsystem. bintafeln soll schon nutzbar sein, bevor
eine Tafel vollständig umsteigt. Eine laufende Synchronisation zweier Systeme ist fehleranfällig.

## Entscheidung

- In der ersten Ausbaustufe ist der Kundenstamm in bintafeln ein **Snapshot**: Jeder Import
  **ersetzt den Bestand vollständig**. In bintafeln werden die Daten nur **gelesen**, nicht
  bearbeitet.
- Der Import ist ein **wiederholbarer Vollaustausch**, keine Synchronisation einzelner
  Datensätze.
- bintafeln kennt nur **ein eigenes, offen dokumentiertes, neutrales CSV-Format**. Jeder Import
  erzeugt einen **Prüfbericht**.
- **Konverter für bestimmte Altsysteme gehören nicht in dieses Repository.**
  *Ergänzt am 2026-11-02 (siehe ADR 0100):* Ein Konverter darf als **zuschaltbares Modul**
  (ADR 0049) in bintafeln aufgenommen werden, wenn mehrere Tafeln dasselbe Altsystem nutzen und
  das Modul das neutrale Importformat erzeugt und durch den normalen Import mit Abgleich schickt.
  Er darf keine festen, tafelspezifischen Werte enthalten und keine Personendaten mitbringen.
  Außerhalb des Repositorys bleiben Konverter weiterhin erlaubt (lokales Werkzeug).
- Erst beim späteren **Umstieg zu einem Stichtag** übernimmt bintafeln die Führung der Daten.

## Begründung

- Ein Vollaustausch ist einfach zu verstehen, zu testen und zu wiederholen. Es gibt keine
  Konflikte zwischen zwei Datenständen.
- Ein neutrales Format hält bintafeln unabhängig von einzelnen Herstellern. Jede Tafel kann
  ihren Export selbst oder mit Hilfe Dritter umwandeln.

## Folgen

- Der Import läuft in einer Transaktion: Entweder wird der ganze neue Bestand übernommen oder
  gar nichts. Ein fehlerhafter Import hinterlässt den alten Stand.
- Andere Module (z. B. Ausgabe) dürfen sich nicht auf Datenbank-IDs der Kundendatensätze
  verlassen, die beim nächsten Import neu entstehen. Sie verweisen über die Kundennummer.
- Vor jedem Import wird gesichert (keine Datenlöschung ohne vorherige Sicherung).
