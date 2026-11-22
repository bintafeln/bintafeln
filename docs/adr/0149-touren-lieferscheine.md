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
- **Aussehen wie der bekannte Vordruck** (vereinfachtes Dokumentationsverfahren nach der
  Verordnung (EG) Nr. 178/2002), gezeichnet mit festen Maßen in `apps/touren/vordruck.py` statt
  über den `Pdf`-Rahmen: oben das Logo der Tafel (ohne Logo ihr Name), Kasten mit Spender/in
  (Station) und Empfänger/in (Tafel), rechts Datum und Nummer, Tabelle mit einer Zeile je
  Warengruppe („-“ ohne Menge), rechts unten die Unterschrift. Keine Kopf- und keine Fußzeile.
  Märkte kennen dieses Blatt; ein anderes Aussehen führt zu Rückfragen.
- **Nummer** fortlaufend aus `TourenEinstellungen.naechste_nummer`, unter Zeilensperre.
- **Versand abschaltbar, mit Testbetrieb** (`TourenEinstellungen.versand`): „ausgeschaltet“
  (Vorgabe – der Lieferschein wird nur gespeichert), „zum Test“ (jede Mail geht mit „[Test]“ im
  Betreff nur an `test_email`, nie an die Station; der Lieferschein gilt weiter als nicht
  verschickt) oder „an die Station“. So lässt sich der Ablauf erproben, ohne dass ein Markt Post
  bekommt; gespeicherte Lieferscheine lassen sich danach in der Liste nachsenden.
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

## Nachtrag: Text der Mail an die Station

Die Märkte kennen die Mail der digitalen Lieferscheine in einer festen Form. Die Vorgabe für
`TourenEinstellungen.mail_text` ist deshalb dieser Wortlaut („Guten Tag! Hiermit erhalten Sie den
Digitalen Lieferschein der {tafel} für folgenden Markt: {station}. Viele Grüße, Ihre {tafel}“),
mit den Platzhaltern `{tafel}` und `{station}`. `lieferscheine.mail_inhalt()` setzt sie ein und
liefert Text und eine schlichte gestaltete Fassung (erste Zeile als Überschrift, Werte maskiert).
Darunter steht automatisch, warum die Station die Mail bekommt, und – mit Domain und hinterlegter
Datenschutzerklärung – der Link dorthin. Kein fremdes Logo, keine Fußzeile eines Verbands.

Wer den früheren Vorgabetext nie geändert hat, bekommt den neuen (Migration `touren/0021`); eigene
Texte bleiben. Texte ohne `{tafel}` bekommen wie bisher den Namen der Tafel darunter.
