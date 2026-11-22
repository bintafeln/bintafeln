# ADR 0152: Touren – Stationen als angefahren kennzeichnen

## Problem

Unterwegs ist in der Tour nicht zu sehen, wo man schon war – außer dort, wo ein Lieferschein
ausgefüllt wurde. Bei langen Touren muss man jedes Mal neu suchen, welche Station als Nächste
kommt. Ausblenden darf man erledigte Stationen nicht: Es kommt vor, dass man noch einmal hin muss.

## Entscheidung

- **„✓ Hier waren wir“** an jeder Station der Tour (`touren.Anfahrt` je Tour, Station und Tag,
  Regeln in `apps/touren/anfahrten.py`). Ein Lieferschein des Tages gilt ebenfalls als
  angefahren. „zurücknehmen“ hebt das Kennzeichen auf.
- **Die Station bleibt stehen**, tritt aber zurück: grau hinterlegt, Haken statt Nummer, mit
  Uhrzeit. Navigation, Telefon und Lieferschein bleiben erreichbar.
- **Sprung zur aktuellen Station:** Beim Öffnen der Tour springt die Seite zur ersten Station
  ohne Kennzeichen (`static/js/tour_aktuell.js`), sobald mindestens eine angefahren ist; die
  Station ist umrandet. Führt die Adresse selbst an eine Stelle (`#halt-3`), bleibt es dabei.
- **Wer darf:** wer an dem Tag auf der Tour eingetragen ist oder das Recht `touren.besetzung`
  hat (`start.darf()`), nur am Tag selbst.
- **Aufbewahrung:** 90 Tage, dann werden die Kennzeichen gelöscht. Sie nennen den Namen der
  Person, die gedrückt hat.

## Begründung

- Ein Fingertipp je Station genügt; die Reihenfolge bleibt frei (man kann eine Station
  überspringen und später anfahren).
- Zurücktreten statt Ausblenden hält die Tour vollständig und zeigt trotzdem auf einen Blick,
  was noch offen ist.
- Die Kennzeichen sind zugleich die Grundlage für den Fortschritt einer Tour, den das Büro
  sehen soll.
