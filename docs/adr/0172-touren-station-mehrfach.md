# ADR 0172: Dieselbe Station mehrfach auf einer Tour

## Problem

Eine Station durfte auf einer Tour nur einmal stehen (ADR 0148). Die Touren fahren aber die
Zentrale und einzelne Ausgabestellen mehrmals an – zum Abladen zwischendurch und noch einmal am
Ende. Beim Einlesen der Stationsfolgen fiel jeder weitere Besuch als „steht doppelt“ weg, und von
Hand ließ er sich auch nicht einplanen.

## Entscheidung

- Die Regel „eine Station je Tour nur einmal“ entfällt (`Halt`). Planung und Import
  (`tourstationen.csv`) nehmen dieselbe Station beliebig oft an; `halt_anhaengen()` hängt immer an.
- `ablauf.halte()` zählt die Besuche durch: `h.durchgang` (der wievielte Besuch der Station) und
  `h.besuche` (wie oft sie vorkommt). Unterwegs steht dann „1. Anfahrt“, „2. Anfahrt“.
- **Jeder Besuch wird für sich abgehakt:** `Anfahrt` bekommt `durchgang`; eindeutig ist Tour,
  Station, Tag und Besuch. Ein Lieferschein des Tages gilt weiter als „angefahren“ – der n-te
  Lieferschein der Station für den n-ten Besuch. Die Regel steht nur in `anfahrten.stand()`;
  Fortschritt, „als Nächstes“ und die Seite der Fahrer nutzen sie.
- Ein Zusatzstopp darf an einer Station liegen, die schon auf der Tour steht (er ist dann ein
  weiterer Besuch); je Station und Tag gibt es weiterhin höchstens einen Zusatzstopp.
- Die Migration ist umkehrbar: Beim Zurückgehen auf eine ältere Version bleibt je Tour der erste
  Besuch einer Station stehen, weitere fallen weg.

## Begründung

So wie gefahren wird, soll die Tour auch im Programm stehen; eine zweite, künstliche Station
„Zentrale (2)“ wäre doppelte Pflege und verfälschte die Statistik je Station. Die Besuche über
ihre Reihenfolge zu zählen statt über den gespeicherten Halt lässt Zusatzstopps (die nicht
gespeichert sind) genauso mitzählen und braucht an der Anfahrt nur eine Zahl.
