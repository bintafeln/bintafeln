# ADR 0149: Touren – Lieferscheine mit Unterschrift am Handy

## Problem

Märkte wollen für jede Abholung einen Lieferschein. Bisher entsteht er auf Papier oder in einem
Portal, das der Markt vorschreibt. Die Tafel will ihn unterwegs am Handy ausfüllen, vom
Ehrenamtlichen unterschreiben lassen und dem Markt per E-Mail schicken; in bintafeln soll er
gespeichert bleiben.

## Entscheidung

- **Ausfüllen an der Station** (`views_lieferscheine.ausfuellen`, Recht `touren.lieferschein`):
  je Warengruppe eine Menge und die Einheit **Kisten oder kg**, eine Anmerkung, die Unterschrift.
  Den Knopf gibt es in der Tour und auf der Seite der Station, wenn die Tafel Lieferscheine
  eingeschaltet hat (`TourenEinstellungen.lieferscheine`) und die Station sie vorsieht
  (`Station.lieferschein`).
- **Warengruppen** (`Warengruppe`) pflegt die Tafel; die Migration liefert sieben als Vorgabe.
  Auf dem Lieferschein steht der Name als Text, damit spätere Umbenennungen alte Scheine nicht
  ändern. Ebenso sind Name und Anschrift der Station und der Name der Tour festgehalten.
- **Unterschrift** mit dem Finger auf einem `<canvas>` (`static/js/unterschrift_feld.js`, ohne
  Bibliothek). Der Server liest das PNG, prüft es (Format, Größe, mindestens ein Strich) und
  speichert es neu ohne Metadaten (`lieferscheine.unterschrift_lesen()`).
- **Das PDF ist der Lieferschein.** Es wird einmal erzeugt (`apps.core.pdf`), verschlüsselt über
  `privatdateien` abgelegt und nie neu berechnet (wie die Ausfertigung in ADR 0130). Die
  Unterschrift selbst wird nicht aufbewahrt. Ein abgeschickter Lieferschein lässt sich nicht
  ändern; ein weiterer am selben Tag kommt dazu.
- **Nummer** fortlaufend aus `TourenEinstellungen.naechste_nummer`, unter Zeilensperre.
- **Versand** nur an die Station (`Station.lieferschein_an`), über `mail.senden()` mit der neuen
  Art „Lieferschein“; niemand in der Tafel bekommt eine Kopie. Fehlt die Adresse oder scheitert
  der Versand, bleibt der Lieferschein gespeichert und trägt den Grund (`mail_fehler`); das Büro
  sendet nach (Recht `touren.lieferscheine`).
- **Erledigt** ist eine Station in der Tour, sobald es für den Tag einen Lieferschein gibt. Ein
  eigenes Abhaken gibt es nicht.
- **Frist:** `TourenEinstellungen.aufbewahrung_jahre` (Vorgabe 10), danach löscht
  `lieferscheine.fristen_anwenden()` samt PDF. Die Auskunft nach Art. 15 nennt die Lieferscheine,
  die eine Person unterschrieben hat.
- **Rechte:** `touren.lieferschein` (ausfüllen, eigene ansehen; Büro, Fahrer, Beifahrer),
  `touren.lieferscheine` (alle ansehen, nachsenden, löschen; Büro), `einstellungen.touren`
  (Admin).

Offen bleibt der Weg über Portale, die einzelne Märkte vorschreiben: Dafür kommt später je
Station eine Wahl des Wegs; bis dahin gibt es nur die E-Mail aus bintafeln.

## Begründung

- Ein festes PDF statt Daten, aus denen man es neu baut: Was der Markt bekommen hat und was
  unterschrieben wurde, bleibt genau so – auch wenn sich Vorlage, Tafelname oder Warengruppen
  ändern.
- Einheit je Zeile wählbar statt je Warengruppe fest: Dieselbe Ware kommt mal in Kisten, mal
  gewogen.
- Speichern geht vor Senden: Unterwegs darf ein fehlender Mailserver oder eine fehlende Adresse
  die Arbeit nicht aufhalten.
