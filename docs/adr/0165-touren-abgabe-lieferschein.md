# ADR 0165: Touren – Lieferschein an jeder Station, auch für Abgaben

Ergänzt ADR 0149 (Lieferscheine) und ADR 0157 (Statistik).

## Problem

Ein Lieferschein ließ sich nur an Stationen ausfüllen, bei denen er vorgesehen war, und immer nur
als Abholung. Es kommt aber vor, dass an einer anderen Station doch Ware mitgeht – und dass die
Tafel selbst Ware abgibt, etwa an eine andere Tafel oder eine Einrichtung.

## Entscheidung

- Ein Lieferschein lässt sich an **jeder** Station ausfüllen, in der Tour und ohne Tour auf der
  Seite der Station (`lieferscheine.moeglich()` hängt nur noch davon ab, ob Lieferscheine
  eingeschaltet sind). `Station.lieferschein` bedeutet nur noch „wird hier regelmäßig erwartet“
  (Statistik „Stationen ohne Lieferschein“).
- `Lieferschein.art`: „Abholung“ (Vorgabe) oder „Abgabe“, gewählt im Formular.
- Bei einer Abgabe sind auf dem PDF Spender und Empfänger vertauscht (die Tafel gibt, die Station
  empfängt), unter der Unterschrift steht „Unterschrift Spender/in“. Sonst bleibt der Vordruck gleich.
- Statistik: Abgaben zählen nicht als abgeholte Menge; sie stehen in einem eigenen Abschnitt
  „Abgaben“ je Empfänger (`statistik.abschnitt_abgaben()`).
- Unverändert: Rechte, fortlaufende Nummer (ein Nummernkreis für beide Arten), Versand,
  Aufbewahrung, „Tourtag zurücksetzen“.

## Begründung

Eine Auswahl im selben Formular hält den Ablauf am Handy gleich. Getrennte Zahlen verhindern, dass
abgegebene Ware die abgeholte Menge aufbläht.
