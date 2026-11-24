# ADR 0159: Touren – neuer Stopp vom Büro, unübersehbar bei der Mannschaft

Ergänzt ADR 0156 (Zusatzstopps) und nutzt ADR 0158 (Push-Nachrichten an Mitarbeitende).

## Problem

Im Lauf des Tages kommen neue Abholaufträge, die das Büro einer laufenden Tour gibt. Bisher stand
der Zusatzstopp dann einfach in der Liste der Tour – wer gerade fährt oder eine andere Seite offen
hat, merkt das nicht. Die Mannschaft muss den neuen Stopp sicher und sofort mitbekommen, und das
Büro muss wissen, ob er angekommen ist.

## Entscheidung

- **Nur Stopps vom Büro:** `Zusatzstopp.vom_buero` ist gesetzt, wenn die Person, die einfügt, an
  dem Tag nicht selbst auf der Tour fährt. Stopps der Mannschaft selbst lösen nichts aus.
- **Push-Nachricht** an die Konten der Mannschaft (`heuler.melden()` → `push.an_benutzer()`), wenn
  der Stopp für heute ist: Tour, Station mit Anschrift, Auftrag; Antippen öffnet die Tour.
  Bekommt, wer die Nachrichten auf „Mein Konto“ eingeschaltet hat.
- **Roter Brief über jeder Seite** (`Modul.kopfzeile`, `static/js/heuler.js`): Die Kopfzeile fragt
  alle 30 Sekunden nach offenen Stopps der eigenen Touren von heute; der Brief erscheint mit
  Rütteln, Ton und Vibration und lässt sich nicht wegdrücken. Für morgen geplante Stopps erscheinen
  am Tag selbst.
- **Bestätigen:** „✓ Gesehen – zur Tour“ bestätigt für die ganze Mannschaft (die erste Bestätigung
  zählt, `gesehen_am`, `gesehen_von_name`) und führt zum Stopp. Bestätigen kann nur, wer mitfährt.
- **Das Büro sieht den Stand** an der Tour: „gesehen 10:12 Uhr von …“ oder „von der Mannschaft
  noch nicht gesehen“.
- **Erst nach „Fahrt beginnen“** (ergänzt): Brief und Push kommen erst, wenn die Mannschaft die
  Fahrt begonnen hat (`heuler.unterwegs()`). Fügt das Büro den Stopp vorher ein, wartet er still
  – in der Tour steht er schon –, und mit dem Beginn der Fahrt holt `heuler.nachholen()` den Push
  nach. Wer noch zu Hause oder im Lager ist, wird nicht mit einem Alarm gestört.

## Begründung

- Push allein reicht nicht: Nicht jede und jeder schaltet sie ein, und das iPhone erlaubt sie nur
  in der App vom Home-Bildschirm. Der Brief in bintafeln erreicht alle, die das Programm offen haben.
- Eine Bestätigung für die Mannschaft statt je Person: Sie sitzt im selben Wagen; das Büro braucht
  nur zu wissen, dass der Stopp angekommen ist. Keine Auswertung je Person.
- Der Brief folgt dem Muster der Post der Verwaltung (ADR 0142), ist aber bewusst aufdringlicher.
