# ADR 0177: Kunden herausnehmen, die lange unentschuldigt gefehlt haben

## Problem

Wer lange nicht gekommen ist und sich nicht gemeldet hat, wird aus der Liste genommen: Ausweis
auf gestern setzen, damit die Kundengruppe frei wird, dann für ein Jahr sperren. Das waren
mehrere Masken je Kunde.

## Entscheidung

- Auf der Kundenseite steht oben rechts in der Karte „Angaben“ der Knopf **„Kunden
  herausnehmen“** – nur mit dem neuen Recht `kunden.herausnehmen` (Vorgabe: Admin) und nur, wenn
  der Kunde die Bedingung „lange nicht gekommen“ erfüllt: seit
  `KundenEinstellungen.herausnehmen_nach_tagen` (Vorgabe 56) keine Abholung oder noch nie, nicht
  schon gesperrt, beendet oder verstorben. Dieselbe Grenze ist die Vorgabe der Liste „Lange
  nicht gekommen“.
- Vor dem Ausführen kommt eine Rückfrage mit letztem Besuch und den Notizen zum Kunden (dort
  stehen Krankmeldungen), Begründung vorbelegt mit „Lange unentschuldigt gefehlt“.
- Die Herausnahme setzt „Ausweis gültig bis“ auf gestern und trägt eine `Sperre` von heute für
  `herausnehmen_sperre_monate` (Vorgabe 12) ein. Kundengruppe (ADR 0061) und Status (ADR 0176)
  folgen daraus über die vorhandenen Regeln. Keine Nachricht an den Kunden.
- **Zurücknehmen:** Die Sperre trägt `herausnahme=True` und das Ausweisdatum von vorher
  (`ausweis_vorher`). „Herausnahme zurücknehmen“ legt die Sperre in den Papierkorb und trägt das
  Datum wieder ein; die Kundengruppe wird nicht von selbst zurückgegeben.
- Regeln nur in `apps/kunden/herausnehmen.py`, alles steht in der Historie.

## Begründung

Der Knopf beim einzelnen Kunden statt in der Liste: Die Entscheidung fällt je Kunde, mit Blick
auf seine Notizen. Ein eigenes Recht, weil die Herausnahme den Kunden für lange Zeit ausschließt.
Bestehende Bausteine (Sperre, Ausweisdatum) statt eines neuen Zustands, damit Einlass, Ampel und
Listen ohne Änderung stimmen.
