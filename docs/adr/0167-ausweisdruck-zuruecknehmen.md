# ADR 0167: Sammeldruck der gemeldeten Ausweise zurücknehmen

## Problem

„Alle gemeldeten Ausweise drucken“ erzeugt ein PDF, erledigt die Meldungen der Ausgabestellen und
schreibt ihnen „Neuer Ausweis ist gedruckt …“. Wird aus der Ferne gedruckt und der Drucker gibt
nichts aus, sind die Meldungen trotzdem erledigt: Man sieht nicht mehr, welche Ausweise noch zu
drucken sind, und die Ausgabestellen haben eine falsche Nachricht.

## Entscheidung

- Der Sammeldruck der gemeldeten Ausweise hält sich als `kunden.Ausweisdruck` fest: wer wann
  welche Kundennummern gedruckt hat, welche Meldungen (`Nachricht`) er erledigt, welche Notizen an
  die Ausgabestellen er geschrieben und welche gemeldeten Notizen er gestrichen hat.
- Auf der Seite „Nachrichten der Ausgabestellen“ steht zu jedem solchen Druck ein Kasten, bis
  jemand mit dem Recht `kunden.ausweis` entscheidet:
  - **„Ja, alle gedruckt“**: Der Druck ist abgeschlossen.
  - **„Nein, zurücknehmen“**: Die Meldungen sind wieder offen, die Notizen „Neuer Ausweis ist
    gedruckt …“ werden entfernt, die gestrichenen Notizen „Neuen Ausweis drucken“ stehen wieder am
    Haushalt. „Alle gemeldeten Ausweise drucken“ bietet dieselben wieder an.
- Die Notiz geht weiter **sofort** an die Ausgabestelle (wie bisher), nicht erst nach der
  Bestätigung. Beim Zurücknehmen verschwindet sie wieder – auch wenn sie dort schon gelesen wurde.
- Der Druck eines einzelnen Ausweises und der Sammeldruck aus der Kundenliste bleiben wie bisher
  ohne diesen Schritt.
- Regeln nur in `apps/kunden/an_stelle.py` (`ausweis_gedruckt(..., merken=True)`,
  `druck_bestaetigen()`, `druck_zuruecknehmen()`). Einträge werden nach 90 Tagen gelöscht.

## Begründung

Der Fehler liegt am Drucker, nicht am Programm; bintafeln kann nicht wissen, ob Papier
herauskam. Deshalb fragt es nach und macht den Druck als Ganzes rückgängig, statt jede Meldung
einzeln wieder zu öffnen. Die sofortige Notiz hält den gewohnten Ablauf: Im Normalfall ist nach
dem Druck nichts weiter nötig als ein Klick auf „Ja“.
