# 0013: Der Einlass erfasst Abholungen schon im Snapshot-Betrieb

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0006, ADR 0011

## Problem

Nach ADR 0006 wird der Kundenstamm in bintafeln nur gelesen, und jeder Import ersetzt ihn
vollständig. Der Einlass soll aber schon jetzt nicht nur prüfen (Ampel), sondern Abholungen und
Ausnahmen auch eintragen. Das kollidiert mit dem Vollaustausch.

## Entscheidung

- Am Einlass eingetragene Abholungen und Ausnahmen werden in bintafeln gespeichert und mit
  `erfasst_am` gekennzeichnet.
- Ein Import ersetzt sie wie alle anderen Teile des Kundenstamms. Der Prüfbericht warnt vorher,
  wie viele in bintafeln erfasste Einträge dabei verloren gehen.
- Personen- und Haushaltsdaten bleiben weiterhin nur lesbar. Einzige weitere Änderung durch den
  Einlass ist das Datum „Letzter Besuch“.
- Eine versehentlich eingetragene Abholung kann am selben Tag zurückgenommen werden. Importierte
  Abholungen lassen sich nicht löschen.
- Ausnahmen am Einlass erteilen dürfen nur Admin und Büro.

## Begründung

Die Tafel plant einen Neustart mit frisch importierten Kunden, ab dem bintafeln führt. Bis dahin
ist ein Verlust der Testerfassungen beim Neuimport gewollt und wird durch die Warnung im
Prüfbericht sichtbar. Eine Synchronisation einzelner Datensätze bleibt damit weiterhin unnötig.
