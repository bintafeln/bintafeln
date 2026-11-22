# ADR 0155: Touren – Meldungen zum Fahrzeug

## Problem

Was den Fahrern am Fahrzeug auffällt – eine defekte Lampe, ein Geräusch, dass getankt wurde –
erreicht die Fahrdienstleitung bisher nur auf Zuruf oder gar nicht. Am Ende einer Tour, wenn
ohnehin der Kilometerstand eingetragen wird, ist der richtige Moment, es festzuhalten.

## Entscheidung

- **Meldung beim Beenden der Tour oder zwischendurch** (`touren.Fahrzeugmeldung`, Regeln in
  `apps/touren/meldungen.py`): Art (Beanstandung/Defekt, Getankt, Anmerkung) und ein kurzer
  Text, am Fahrzeug und an der Fahrt des Tages. Melden darf, wer die Fahrt fahren darf
  (`start.darf()`), am Tag der Fahrt.
- **Die Fahrdienstleitung sieht offene Meldungen auf der Startseite** (`Modul.startseite`, für
  alle mit dem Recht `touren.fahrten`) und in der Liste „Touren → Meldungen zum Fahrzeug“,
  nach Fahrzeug filterbar. „✓ Erledigt“ hakt ab, auf Wunsch mit einer Notiz, was getan wurde;
  erledigte lassen sich wieder öffnen.
- **Keine Mail.** Die Startseite ist der Ort, an dem die Fahrdienstleitung ohnehin beginnt; eine
  Mail je getanktem Fahrzeug wäre Lärm.
- **Aufbewahrung:** erledigte Meldungen wie Fahrten und Lieferscheine
  (`TourenEinstellungen.aufbewahrung_jahre`), offene bleiben, bis jemand sie abhakt. Die Auskunft
  nach Art. 15 nennt, was jemand gemeldet hat.

## Begründung

- Ein Feld an der Stelle, an der die Fahrer schon den Kilometerstand eintippen, kostet sie
  nichts und geht nicht vergessen.
- Fahrzeug und Tour stehen als Text in der Meldung, damit sie lesbar bleibt, wenn das Fahrzeug
  abgeschafft oder die Tour umbenannt wird.
- „Getankt“ ist bewusst nur eine Art der Meldung, kein eigenes Tankbuch mit Litern und Preisen –
  das käme erst, wenn jemand es auswerten will.
