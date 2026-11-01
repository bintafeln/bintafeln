# 0064: Hochgeladene Fotos einstellbar verkleinern

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Quittungen, Dokumente zum Haushalt, Spendenbelege, Führerscheinkopien und Anhänge von Anträgen
kommen meist als Handyfoto mit 3–5 MB. Über Jahre aufbewahrt (z. B. Quittungen fünf Jahre) und
dazu in jeder Sicherung, füllen sie einen kleinen Server schnell. Wie stark verkleinert werden
darf, hängt von der Tafel ab (Lesbarkeit, Platz).

## Entscheidung

- `FotoEinstellungen` (Singleton): längste Seite (aus einer Auswahl, auch „nicht
  verkleinern“), Qualität in Prozent und wahlweise Graustufen. Vorgabe 1600 Pixel, 75 %.
- `privatdateien.speichern()` verkleinert jedes Foto (JPEG, PNG, WebP) vor dem Verschlüsseln
  nach diesen Einstellungen; das Format bleibt, damit der gespeicherte Dateityp stimmt. PDFs
  bleiben unverändert. Ist das Ergebnis nicht kleiner, bleibt das Original.
- Seite „Einstellungen → Systemsteuerung → Speicher und Fotos“ (Recht „Tafel-Einstellungen“):
  Einstellung, belegter Platz (Datenbank, Dateien je Ordner, aufbewahrte Originale), vorhandene
  Fotos nachträglich verkleinern (je Klick bis zu 200). Quelle ist immer das Original, das als
  `.orig` daneben liegen bleibt; so lassen sich geänderte Einstellungen erneut anwenden, und
  „nicht verkleinern“ stellt die Originale wieder her. Welche Datei mit welchen Einstellungen
  verkleinert ist, steht in `privat/verkleinert.json`.
- Platz frei wird erst mit „Originale löschen“; das geht nur, wenn eine Sicherung höchstens
  24 Stunden alt ist, und nicht in der Demo.

## Begründung

Für Quittungen und Bescheide genügen 1600 Pixel; das spart etwa neun Zehntel. Weil die Tafel
selbst entscheidet und die Originale erst nach einer Sicherung verschwinden, geht nichts
unbemerkt verloren.

## Nachtrag: Alle Dateien (2026-10-27)

`privatdateien.verzeichnis()` listet alle Dateien unter `privat/` und ordnet sie über
`PRIVATDATEI = (ordner, feld)` ihren Datensätzen zu (dazu jetzt auch Antragsnachweise und
Führerscheinkopien). Status: gehört zu einem Datensatz, im Papierkorb, verwaist (bekannter Ordner,
kein Datensatz) oder unbekannter Ordner. `verwaiste_loeschen()` löscht nur verwaiste Dateien, die
älter als ein Tag sind, und nur nach einer höchstens 24 Stunden alten Sicherung; unbekannte
Ordner nie. Die Seite zeigt keine Inhalte.

## Nachtrag: Bilder der Tafel ansehen (2026-11-01)

Die öffentlichen Bilder der Tafel (Logo, App-Symbol, Hintergrund der Anmeldeseite und der
übrigen Seiten, weitere Hintergrundbilder) liegen in den Tafel-Einstellungen verstreut. Damit
man sieht, was hinterlegt ist, zeigt die Seite „Speicher und Fotos“ sie als kleine Galerie mit
Vorschau und Dateigröße (`views_speicher.tafel_bilder()`); ein Klick öffnet das Bild in voller
Größe. Von den Tafel-Einstellungen führt ein Verweis dorthin. Nur Ansehen, kein Hochladen oder
Löschen – das bleibt bei den Tafel-Einstellungen. Die Bilder sind ohnehin öffentlich abrufbar
(`oeffentlich/`), deshalb entsteht keine neue Offenlegung.
