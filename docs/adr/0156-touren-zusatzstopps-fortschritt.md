# ADR 0156: Touren – Zusatzstopps, Fortschritt, Lieferscheine nur für die eigene Tour

## Problem

Im Lauf des Tages kommen laufend Abholaufträge dazu. Bisher ließ sich eine fahrende Tour nicht
ergänzen, ohne ihre feste Stationsfolge zu ändern, und das Büro sah nicht, wie weit eine Tour
ist. Die Mannschaft soll einen Stopp auch selbst einfügen können. Außerdem waren Lieferscheine
einer Tour für alle zu sehen, die Touren fahren dürfen.

## Entscheidung

- **Zusatzstopp je Tour und Tag** (`touren.Zusatzstopp`, Regeln in `apps/touren/zusatz.py`): eine
  Station aus der Liste oder eine **freie Adresse**, die dabei als Station angelegt wird; dazu
  „Was ist zu tun?“. Er kommt „als Nächstes“ hinter die schon angefahrenen Stationen oder ans
  Ende. Die feste Stationsfolge (`Halt`) bleibt unberührt.
- **Einreihen ohne Sonderweg:** `ablauf.halte(tour, datum)` liefert Zusatzstopps als nicht
  gespeicherte `Halt`-Objekte (`h.zusatz`). Navigation, „Hier waren wir“, Lieferschein, Route und
  Fortschritt behandeln sie wie jede Station.
- **Wer darf:** die Mannschaft nur an der eigenen Tour und nur am Tag selbst; wer das Recht
  `touren.besetzung` hat (Büro), an jeder Tour, die an dem Tag fährt. Geprüft in
  `zusatz.einfuegen()`. Entfernen geht über den Papierkorb.
- **Fortschritt** (`anfahrten.fortschritt()`): „Touren heute“ zeigt je Tour, wie viele Stationen
  angefahren sind, die nächste Station und den Stand der Fahrt.
- **Lieferscheine nur für die eigene Tour:** Wer nicht auf der Tour fährt, sieht dort weder
  Lieferscheine noch den Knopf zum Ausfüllen – nur, dass die Station angefahren wurde. Das PDF
  öffnet, wer es ausgefüllt hat oder an dem Tag auf dieser Tour gefahren ist
  (`lieferscheine.darf_sehen()`); mit dem Recht `touren.lieferscheine` (Büro) alle.
- **Aufbewahrung:** Zusatzstopps 90 Tage.

## Begründung

- Ein Stopp für einen Tag ist etwas anderes als eine Änderung der Tour; getrennte Daten halten
  die feste Reihenfolge sauber.
- Die freie Adresse als Station anzulegen, statt eine zweite Art von Stopp zu erfinden, hält
  alles Weitere (Navigation, Lieferschein) ohne Sonderfälle; das Büro kann die Station später
  ergänzen oder ausschalten.
- Lieferscheine nennen, was ein Markt gespendet hat – das geht nur die an, die dort waren, und
  das Büro.
- Die Benachrichtigung der Mannschaft über einen neuen Stopp (Push) folgt getrennt.
