# ADR 0163: Touren – beim Abhaken sagen, was war

Ergänzt ADR 0152 („Hier waren wir“) und ADR 0157 (Statistik).

## Problem

„Hier waren wir“ hakte eine Station ohne Lieferschein nur ab. Warum es nichts gab, stand nirgends:
keine Ware, Markt geschlossen, von anderen blockiert? Für die Planung ist genau das wichtig.

## Entscheidung

- Der Knopf heißt „Ohne Lieferschein abhaken“. Die Mannschaft wählt den **Umstand** und kann eine
  kurze Anmerkung dazuschreiben.
- Die Liste pflegt jede Tafel selbst (`touren.Umstand`: Name, Reihenfolge, aktiv, „Anmerkung
  nötig“) unter „Touren → Einrichten“. Vorgabe per Migration: Abgeholt, Keine Ware, Markt
  geschlossen, Blockiert durch andere, Sonstiges (mit Pflicht-Anmerkung).
- Umstand und Anmerkung stehen als Text in der `Anfahrt` (`umstand`, `anmerkung`), so wie sie beim
  Abhaken hießen; spätere Änderungen der Liste ändern alte Einträge nicht. Regeln nur in
  `apps/touren/anfahrten.py` (`umstaende()`, `markieren()`).
- Sind alle Umstände ausgeschaltet, wird wie bisher ohne Auswahl abgehakt.
- Statistik: Abschnitt „Ohne Lieferschein abgehakt“ zählt je Station, wie oft welcher Umstand
  vorkam (`statistik.abschnitt_umstaende()`) – nie je Person.
- Fristen: Nach 90 Tagen wird der Name dessen gelöscht, der abgehakt hat. Einträge ohne Umstand
  verschwinden dann ganz (wie bisher); Einträge mit Umstand bleiben für die Statistik so lange wie
  die Lieferscheine (`TourenEinstellungen.aufbewahrung_jahre`).
- Keine Sofort-Nachricht ans Büro; das Büro sieht den Umstand in der Tour des Tages und in der
  Statistik.

## Begründung

Auswahl statt Freitext macht die Angaben auswertbar; die eigene Liste je Tafel deckt örtliche
Besonderheiten ab. Der Text in der Anfahrt hält alte Einträge stabil. Ohne Namen ist die lange
Aufbewahrung unbedenklich und entspricht der Regel, nie je Person auszuwerten.
