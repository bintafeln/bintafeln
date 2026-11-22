# ADR 0150: Touren – Besetzung beim Tourstart bestätigen

## Problem

Die Tour am Handy zeigt die Besetzung aus dem Fahrerplan. Ob wirklich diese Personen im Wagen
sitzen, weiß bintafeln nicht: Kurzfristige Wechsel werden oft nur zugerufen und stehen nirgends.
Außerdem fahren viele Touren je Wochentag in anderer Reihenfolge („Montag Nordtour“), gehören
aber zu einer Tour des Fahrerplans („Nordtour“).

## Entscheidung

- **Frage vor der Tour.** Wer am heutigen Tag eine Tour aus dem Fahrerplan öffnet, sieht zuerst
  „Seid ihr Peter und Paul?“ mit den Namen aus dem Fahrerplan (`apps/touren/start.py`,
  `views_touren.start`). „Ja, stimmt“ hält die Bestätigung fest (`Tourstart`: Tour, Tag, wer,
  wann) und öffnet die Tour. Eigene und kurzfristige Touren fragen nicht.
- **Berichtigen schreibt in den Fahrerplan.** „Nein, ändern“ bietet je Platz die Personen an,
  die an dem Tag einspringen können (`fahrdienst.plan.verfuegbar()`, auf den Fahrerplatz nur
  Fahrer). Die Wahl wird für diesen Tag als `Ersatz` in den Fahrerplan geschrieben – Plan,
  Aushang und Tour zeigen dasselbe, es gibt keine zweite Wahrheit.
- **Kein Fremder trägt sich ein.** Bestätigen und ändern darf nur, wer an dem Tag selbst auf der
  Tour eingetragen ist; nach der Änderung muss diese Person weiter auf der Tour stehen (niemand
  nimmt sich selbst heraus). Wer nicht eingetragen ist, sieht die Tour wie bisher mit dem Vermerk
  „Besetzung noch nicht bestätigt“. Das neue Recht `touren.besetzung` (Vorgabe: Büro) erlaubt
  beides für jede Tour. Geprüft wird in `start.bestaetigen()`, nicht nur in der Ansicht.
- **Wochentag im Namen.** Eigene Fahrtage einer Tour aus dem Fahrerplan grenzen jetzt ein
  (`ablauf.faehrt_am()`): Sie fährt, wenn die Tour im Fahrerplan fährt *und* der Tag angehakt ist.
  Der Import verbindet „Montag Nordtour“ mit „Nordtour“ und setzt den Fahrtag
  (`importieren_touren.wochentag_im_namen()`). Bisher wirkungslose Fahrtage verbundener Touren
  leert die Migration, damit keine vorhandene Tour seltener fährt.
- **Aufbewahrung.** `Tourstart` enthält nur den Namen der bestätigenden Person und wird nach
  90 Tagen gelöscht (`start.fristen_anwenden()`).

## Begründung

- Die Frage kostet einen Fingertipp und fängt genau die Wechsel ab, die sonst niemand einträgt.
- In den Fahrerplan zurückzuschreiben hält eine Quelle für „wer fährt“; eine eigene Besetzung an
  der Tour würde vom Plan abweichen.
- Die Schutzregel folgt dem Wunsch, dass sich niemand in eine Tour einträgt, auf der er nicht
  ist: Die Mannschaft regelt ihren eigenen Wagen, alles andere das Büro.
- Gäste ohne Konto lassen sich am Handy nicht eintragen; das bleibt im Fahrerplan.
