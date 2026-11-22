# ADR 0162: Touren – einen ganzen Tourtag zurücksetzen

Ergänzt ADR 0149 (Lieferscheine), 0151 (Fahrten), 0152, 0155, 0156.

## Problem

Beim Ausprobieren entstehen Testtouren: eine Fahrt mit erfundenem Kilometerstand, Lieferscheine,
abgehakte Stationen, Zusatzstopps, Meldungen. Einzeln ließen sich nur die Fahrt und Lieferscheine
löschen; der Rest blieb stehen und verfälschte Fahrtenbuch und Statistik.

## Entscheidung

- `apps/touren/tourtag.py`: `zuruecksetzen(tour, datum, benutzer)` legt **alles**, was an dem Tag
  zu der Tour eingetragen wurde, in den Papierkorb: Fahrt, Lieferscheine, „Hier waren wir“,
  Zusatzstopps, Meldungen zum Fahrzeug der Fahrt, bestätigte Besetzung.
- **Ein** Eintrag im Papierkorb („Tourtag“); von dort kommt alles gemeinsam zurück.
- Der Kilometerstand des Fahrzeugs geht wie beim Löschen einer Fahrt auf den Stand davor zurück
  (`fahrten.stand_zurueck()`).
- Die Tour selbst, ihre Stationen und – bei einer Tour aus dem Fahrerplan – ein dort eingetragener
  Ersatz bleiben.
- **Rechte:** `touren.fahrten` und `touren.lieferscheine` zusammen. Die Mannschaft kann es nicht.
- Der Knopf steht unten in der geöffneten Tour des Tages und zeigt vorher, was verschwindet; er
  erscheint nur, wenn etwas eingetragen ist.
- Die Statistik hat keine eigenen Daten; sie rechnet aus Lieferscheinen und Fahrten und stimmt
  danach von selbst.

## Begründung

- Lieferscheine sind Belege nach der Lebensmittel-Basisverordnung. Deshalb Papierkorb statt
  endgültigem Löschen, und deshalb das Recht, das auch einzelne Lieferscheine löschen darf.
- Ein gemeinsamer Eintrag statt sechs: Was zusammen entstand, kommt zusammen zurück.
- Schon verschickte Mails lassen sich nicht zurückholen; das steht am Knopf.
