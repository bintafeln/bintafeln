# ADR 0138: Grafiken in Serienbrief-Vorlagen

## Problem

In Serienbriefen sollen Grafiken und Bilder im Text stehen können: ein Logo über der Einladung, ein
Foto vom Sommerfest im Dankesbrief, eine Grafik neben einer Ankündigung. Im gedruckten Brief
(PDF) und in der Serien-Mail sollen sie an derselben Stelle im Text erscheinen, nicht als
separater Anhang. Der Editor (ADR 0088) kannte bisher nur Bilder über eine Internet-Adresse, und
dieser Knopf war für Serienbriefe ausgeblendet.

## Entscheidung

- Bilder werden in bintafeln hochgeladen und als `serienbriefe.Grafik` gespeichert (Datei unter
  `MEDIA_ROOT/serienbriefe/grafiken/`, damit auch in der Datensicherung). Beim Hochladen
  (`grafiken.speichern()`) wird das Bild gedreht wie fotografiert, auf höchstens 2000 Pixel
  verkleinert und neu gespeichert: Fotos als JPEG, alles andere als PNG (Transparenz bleibt).
  Metadaten wie Aufnahmeort oder Kamera fallen dabei weg. Höchstens 8 MB.
- Im Vorlagentext steht ein normales `<img>` mit der Adresse `serienbriefe:grafik` und der Größe
  als `width` in Prozent der Textbreite: klein 25 %, mittel 50 %, ganze Breite 100 %.
  Ausgerichtet wird wie Text, über „Links“, „Mitte“ oder „Rechts“ des Absatzes.
- Im Editor öffnet der Knopf „Grafik“ einen Dialog: vorhandene Grafiken antippen oder eine neue
  hochladen, Größe wählen. Ein Klick auf eine Grafik im Text zeigt „Grafik ändern“ (Größe,
  entfernen). Grafiken lassen sich im Dialog löschen, sie landen im Papierkorb.
- **PDF:** `gestaltung.flowables()` setzt die Grafik als eigenes Bild in der gewählten Breite
  und Ausrichtung, höchstens 200 mm hoch.
- **Mail:** `grafiken.fuer_mail()` ersetzt die Adresse durch einen `cid:`-Verweis.
  `mail.senden(..., bilder=…)` legt die Bilder mit dem HTML in ein `multipart/related`. So steht
  das Bild im Text der Mail; PDF-Anhänge (Dankesbriefe) bleiben daneben normale Anhänge.
- Nur eigene Grafiken werden gezeichnet oder eingebettet. Bildadressen aus dem Internet werden
  weder im PDF noch in der Mail abgerufen und fallen weg.
- Recht: `serienbriefe.erstellen` für Hochladen, Anzeigen und Löschen.

## Begründung

Hochgeladene Bilder machen den Brief unabhängig von fremden Servern. Bilder aus dem Internet
müsste der Server beim Drucken abrufen; das wäre ein Einfallstor (Abrufe in das eigene Netz)
und machte den Brief von fremden Seiten abhängig. In Mails würden Bilder über eine Adresse von
vielen Mailprogrammen erst nach Rückfrage geladen. Eingebettete Bilder (`cid:`) zeigen sie
direkt im Text.

Die Größe in Prozent der Textbreite wirkt im Editor, im PDF und in der Mail gleich. Drei feste
Größen sind einfacher als freies Ziehen und genügen für Briefe. Das Neuspeichern beim Hochladen
hält die Datensicherung klein und entfernt unbemerkt mitgeschickte Angaben aus Fotos, etwa den
Aufnahmeort.
