# ADR 0151: Touren – Fahrten mit Fahrzeug und Kilometerstand

## Problem

bintafeln weiß, welche Touren es gibt und welche Lieferscheine entstanden sind, aber nicht, ob
und wie weit tatsächlich gefahren wurde. Für die Statistik der Touren (Fahrten, Kilometer,
Dauer) und für ein Fahrtenbuch je Fahrzeug fehlen die Daten.

## Entscheidung

- **Fahrt je Tour und Tag** (`touren.Fahrt`): Wer die Tour fährt, drückt vor der Abfahrt „Fahrt
  beginnen“ und nach der Tour „Tour beenden“. Festgehalten werden Tour, Tag, Fahrzeug, Besetzung
  (als Text), Beginn, Ende und wer gedrückt hat.
- **Kilometerstand eintippen**, bei Abfahrt und Ankunft. Die gefahrenen Kilometer sind die
  Differenz. bintafeln schlägt den letzten bekannten Stand des Fahrzeugs vor
  (`static/js/fahrt_km.js`) und weist offensichtliche Tippfehler zurück (Ankunft kleiner als
  Abfahrt, mehr als 1500 km an einem Tag).
- **Fahrzeugliste** (`touren.Fahrzeug`, Name, Kennzeichen, aktiv) in den Einstellungen der
  Touren. Gibt es aktive Fahrzeuge, ist die Wahl Pflicht; ohne Liste wird nur der
  Kilometerstand gefragt.
- **Kein Ort wird geprüft.** Beendet wird, wo das Fahrzeug stehen bleibt – bei vielen Tafeln an
  der Zentrale, bei anderen am Lager oder an einer Ausgabestelle.
- **Wer darf:** wer an dem Tag auf der Tour eingetragen ist oder das Recht `touren.besetzung`
  hat (dieselbe Regel wie beim Bestätigen der Besetzung, ADR 0150). Geprüft in
  `fahrten.beginnen()`/`beenden()`.
- **Fahrtenbuch fürs Büro** (Recht `touren.fahrten`, Vorgabe Büro): Liste mit Filter nach
  Fahrzeug und Zeitraum, Summe der Kilometer, CSV, und „Berichtigen“ für Fahrzeug und
  Kilometerstände – mit Vermerk, wer berichtigt hat. Nicht beendete Fahrten früherer Tage sind
  als „ohne Kilometerstand bei Ankunft“ zu finden und werden nachgetragen.
- **Aufbewahrung** wie Lieferscheine (`TourenEinstellungen.aufbewahrung_jahre`); die Auskunft
  nach Art. 15 nennt die Fahrten, die jemand begonnen oder beendet hat.

## Begründung

- Der abgelesene Kilometerstand ist genau und braucht keinen Kartendienst, an den Adressen der
  Stationen gingen; eine geschätzte Strecke wäre nur eine Näherung.
- Zwei Eingaben je Tour sind zumutbar und ergeben nebenbei das Fahrtenbuch.
- Eine Ortsbindung über den Standort des Handys wäre fehleranfällig und würde zusätzliche Daten
  über die Fahrer erzeugen.
- Namen von Tour und Fahrzeug stehen als Text in der Fahrt, damit die Statistik stimmt, wenn
  eine Tour umbenannt oder ein Fahrzeug abgeschafft wird.
