# ADR 0183: Zwei-Faktor selbst neu einrichten

## Problem

Wer die Zwei-Faktor-Anmeldung schon nutzt und ein neues Handy oder eine andere Authenticator-App
bekommt, konnte nicht selbst wechseln. Ohne Pflicht blieb nur „abschalten und neu einrichten“,
bei Pflicht-Rollen musste ein Admin zurücksetzen – und wer setzt den einzigen Admin zurück?

## Entscheidung

- „Mein Konto“ bekommt **„Zwei-Faktor neu einrichten“**, auch für Pflicht-Rollen.
- Vorher weist man sich mit einem **gültigen Code** aus: aus der bisherigen App oder ein
  Notfallcode. Die Freigabe liegt 15 Minuten in der Sitzung (`zwei_faktor.neu_freigeben()`).
- Dann die gewohnte Einrichtung mit neuem QR-Code. **Das bisherige Gerät gilt, bis das neue mit
  seinem ersten Code bestätigt ist** (`einrichtung_bestaetigen()` entfernt es erst dann). Wer
  abbricht, behält alles wie bisher.
- Danach gibt es neue Notfallcodes, die alten gelten nicht mehr; vertraute Geräte fragen wieder
  nach dem Code.
- Ohne Handy und ohne Notfallcode bleibt das Zurücksetzen durch Admin oder Büro (ADR 0015).

## Begründung

Eine angemeldete Sitzung allein darf den zweiten Faktor nicht austauschen können – sonst genügte
ein unbeaufsichtigter Browser. Der Code davor verlangt genau das, was der zweite Faktor schützen
soll. Dass das alte Gerät bis zur Bestätigung gilt, verhindert, dass sich jemand mitten im Wechsel
aussperrt.
