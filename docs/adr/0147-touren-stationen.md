# ADR 0147: Modul Touren – Stationen

## Problem

Der Fahrdienst (ADR 0074) plant, **wer** fährt. **Wohin** gefahren wird – Märkte, Bäckereien,
Lieferanten, Lager – stand bisher nur im Altsystem und auf Papier. Die Tafel will die Stationen
in bintafeln führen, Touren daraus zusammenstellen, an jeder Station eine Navigation starten und
dort Lieferscheine ausfüllen, die der Markt per Mail bekommt.

## Entscheidung

Ein zuschaltbares Modul `touren` (ADR 0049), in mehreren Schritten. Dieser ADR beschreibt den
ersten: die Stationen.

- **Eigene Liste `Station`, nicht das Adressbuch.** Stationen kommen gesammelt aus dem
  bisherigen System, tragen Angaben, die im Adressbuch keinen Platz haben (Abholtage, Anfahrt,
  Adresse für Lieferscheine, Kennung), und werden von anderen Leuten gepflegt als das Adressbuch
  (Fahrdienstleitung statt Spenden/Serienbriefe).
- **Übertragen ins Adressbuch** (`apps/touren/adressbuch.py`): einmalig, auf Knopfdruck, einzeln
  oder für alle aktiven Stationen. Angelegt wird eine Organisation; als Kategorie die Art der
  Station. Gibt es schon eine Organisation mit gleichem Namen und gleicher PLZ, wird sie
  verknüpft. `Station.adresse` merkt den Eintrag; danach laufen beide getrennt weiter.
- **Import** (`apps/touren/importieren.py`, Format in `docs/importformat-touren.md`): Die
  `kennung` entscheidet zwischen neu und aktualisieren. Nur gefüllte Zellen überschreiben, nichts
  wird gelöscht. Prüfbericht vor dem Übernehmen wie beim Adressbuch (ADR 0044); der Import steht
  über `Modul.datenimport` auf der Seite „Daten importieren“. Der CSV-Export schreibt dasselbe
  Format.
- **Navigation nur als Link zu Google Maps** (`Station.navigation`,
  `https://www.google.com/maps/dir/?api=1&destination=…`): kein API-Schlüssel, keine Karte in
  bintafeln, keine Geokodierung. Ziel ist die Anschrift; nur wenn die nicht zur richtigen
  Zufahrt führt, trägt man Koordinaten ein.
- **Rechte:** `touren.stationen` (sehen und navigieren; Vorgabe Büro, Fahrer, Beifahrer) und
  `touren.stationen_bearbeiten` (pflegen, importieren, löschen; Vorgabe Büro). Ins Adressbuch
  übertragen braucht zusätzlich `adressen.bearbeiten`.

Geplant sind danach: Touren mit Stationen in Fahrtreihenfolge (mit oder ohne Bezug zu einer
Tour des Fahrdienstes, auch kurzfristige Touren für einen Tag) und Lieferscheine je Station. Für
die Lieferscheine wählt die Tafel später je Station den Weg (Mail aus bintafeln oder das Portal,
das ein Markt vorschreibt); bis dahin sagt `Station.lieferschein` nur, ob einer ausgefüllt wird.

## Begründung

- Ein Link statt einer eingebauten Karte: Die Fahrer haben die Navigations-App ohnehin auf dem
  Handy, bintafeln braucht keinen Vertrag mit einem Kartendienst, und es fließen keine Daten zu
  Google, bevor jemand den Knopf antippt.
- „Leere Zellen ändern nichts“ schützt von Hand gepflegte Angaben, wenn ein Auszug aus dem
  bisherigen System unvollständig ist; dafür lässt sich ein Feld per Import nicht leeren – das
  geht in der Oberfläche.
- Das Verknüpfen über Name und PLZ verhindert Dubletten im Adressbuch, wenn ein Markt dort schon
  als Spender steht.
