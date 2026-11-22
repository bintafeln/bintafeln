# ADR 0154: Touren – Routenvorschau in der Planung, Zentrale als Start und Ziel

Ergänzt ADR 0147 („Navigation nur als Link zu Google Maps, kein Schlüssel, keine Karte“).

## Problem

Beim Zusammenstellen einer Tour ist nicht zu sehen, wie sie tatsächlich gefahren wird – ob die
Reihenfolge der Stationen sinnvoll ist oder kreuz und quer führt. Touren beginnen und enden bei
den meisten Tafeln an der Zentrale; das wusste bintafeln bisher nicht.

## Entscheidung

- **Zentrale als Start und Ziel:** `TourenEinstellungen.zentrale` (leer = Anschrift der Tafel;
  abschaltbar mit `zentrale_aus`). Die Route am Handy endet dort (`ablauf.routen(…, zentrale)`,
  Start bleibt der eigene Standort); die Vorschau der Planung beginnt und endet dort.
- **Vorschau nur in der Planung** (Seite der Tour und Maske der kurzfristigen Tour), als
  Baustein `touren/_karte.html` aus `ablauf.vorschau()`. Die Fahrer bekommen sie nicht.
- **Ohne Einrichtung:** ein Link, der die Route in einem eigenen Google-Maps-Fenster öffnet
  (höchstens neun Zwischenstopps je Link, längere Touren in Abschnitten).
- **Eingebettete Karte nur mit eigenem Schlüssel der Tafel** (Google „Maps Embed API“,
  kostenlos), eingetragen vom Admin, verschlüsselt über `apps.core.geheimnis`
  (`karten_schluessel_verschluesselt`, nie wieder angezeigt, nicht im Änderungsprotokoll).
  Höchstens 20 Zwischenstopps je Karte, längere Touren in Abschnitten.
- **Erst nach Klick:** Die Karte wird erst mit „Karte zeigen“ geladen
  (`static/js/tour_karte.js`); die Wahl merkt sich das Gerät (localStorage
  `bintafeln-tourkarte`) und lässt sich wieder abstellen. Vorher geht nichts an Google.
- An Google gehen dabei nur Anschriften der Stationen und der Zentrale – keine Personendaten,
  keine Kundendaten. Der Verweis der Seite wird auf die Herkunft gekürzt (`strict-origin`),
  damit ein auf die eigene Adresse beschränkter Schlüssel funktioniert.

## Begründung

- Die Fahrdienstleitung will die Route sehen, während sie plant; ein Fenster in der Seite ist
  dafür deutlich bequemer als ein Link.
- Ein eigener Schlüssel je Tafel hält bintafeln frei von einem zentralen Google-Konto und von
  Kosten; ohne Schlüssel bleibt der Link, sodass niemand etwas einrichten muss.
- Eine eigene Karte (OpenStreetMap mit Routenberechnung) bräuchte Geokodierung der Anschriften
  und fremde Dienste mit Nutzungsgrenzen – mehr Aufwand für weniger vertrautes Ergebnis.
- Laden erst nach Klick hält die Zusage aus ADR 0147, dass das bloße Öffnen einer Seite keine
  Daten an Google schickt.
