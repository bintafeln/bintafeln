# ADR 0171: Ausgabestellen der Tafel als Stationen der Touren

## Problem

Die Touren fahren nicht nur Märkte an, sondern auch die eigenen Ausgabestellen und die Zentrale –
am Anfang, am Ende oder zwischendrin, um Ware abzugeben. Stationen sind eine eigene Liste
(ADR 0147); die Ausgabestellen dort noch einmal von Hand einzutippen wäre doppelte Pflege, und
nach einer Änderung stimmten die beiden Stellen nicht mehr überein.

## Entscheidung

- Zu jeder **aktiven Ausgabestelle mit Anschrift** (Straße, PLZ, Ort) gibt es automatisch eine
  **Station** (Art „Ausgabestelle“, Kennung `AS-<Nummer>`, `Station.ausgabestelle`).
  `apps/touren/ausgabestellen.py` (`abgleichen()`) legt sie an und hält sie aktuell – beim Öffnen
  der Stationsliste und mit dem täglichen Lauf des Moduls (`Modul.fristen`).
- **Aus der Ausgabestelle** kommen Name, Anschrift, Telefon, E-Mail und ob sie aktiv ist. Diese
  Felder sind an der Station gesperrt und werden an der Ausgabestelle geändert. „Straße und
  Hausnummer“ der Ausgabestelle wird dabei in Straße und Hausnummer geteilt.
- **An der Station** bleibt alles, was nur die Fahrer betrifft: Anfahrt, Abholzeit, Lieferschein,
  Notiz, Koordinaten. Der Abgleich fasst das nicht an. Neue Stationen dieser Art haben
  „Lieferschein“ zunächst aus.
- Wird eine Ausgabestelle abgeschaltet oder geschlossen, wird die Station abgeschaltet – nie
  gelöscht; sie lässt sich in der Stationsliste auch nicht löschen.
- Hat jemand die Ausgabestelle schon von Hand als Station angelegt (Art „Ausgabestelle“, gleicher
  Name), wird diese verknüpft statt eine zweite anzulegen.
- Ausgabestellen ohne vollständige Anschrift bekommen keine Station; die Stationsliste nennt sie.

## Begründung

Eine Quelle für Name und Anschrift, keine doppelte Eingabe. Die Verknüpfung liegt im Modul Touren
(der Kern kennt keine Stationen, ADR 0049); deshalb zieht das Modul die Daten, statt dass die
Ausgabestelle sie schiebt. Ein Abgleich bei jedem Öffnen der Liste ist bei den wenigen
Ausgabestellen einer Tafel billig und braucht keine Signale.
