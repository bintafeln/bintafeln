# ADR 0112: Dokumentart erkennen (Amtsdokument statt Ausweis)

## Problem

Die Ausweisprüfung (ADR 0107) liest die MRZ eines Ausweises. Viele Antragstellende hängen aber
**gar keinen Ausweis** an, sondern nur **behördliche Bescheide** (Bürgergeld, Grundsicherung,
Wohngeld …) oder andere Dokumente. Darin steht keine Staatsangehörigkeit – die Prüfung findet
nichts (`erkannt=False`). Bisher landeten diese Fälle unterschiedslos im großen Topf „nichts
erkannt“, und es ließ sich nicht unterscheiden, ob ein **unlesbarer Ausweis** vorliegt (lohnt einen
Blick) oder nur ein **Amtsdokument** (kann man sich sparen). Bei vielen Anträgen ist das viel
unnötige Handarbeit.

## Entscheidung

bintafeln ordnet jeden geprüften Antrag beim Scan in eine **Dokumentart** ein (neues, abgeleitetes
Feld `Antrag.ausweis_befund`):

- `abweichung` – Ausweis gelesen, Staatsangehörigkeit weicht ab (= der bekannte Hinweis),
- `passt` – Ausweis gelesen, passt zur Angabe,
- `amtsdokument` – **kein** Ausweis erkannt, aber typische Bescheid-Wörter im Text gefunden,
- `unklar` – Nachweis vorhanden, nichts erkannt und kein Bescheid – evtl. unlesbarer Ausweis,
- `ohne` – kein Bild-/PDF-Nachweis,
- `""` – (noch) nicht eingeordnet.

Die Erkennung des Amtsdokuments läuft **lokal** wie die MRZ-Prüfung (kein externer Dienst, kein KI):
nur **wenn kein Ausweis erkannt wurde**, liest ein zusätzlicher, freier OCR-Durchgang
(`ausweis_pruefung._ocr_text`, Deutsch+Englisch) den Text und sucht nach eindeutigen Stichwörtern
(`AMTSDOKUMENT_WOERTER`: Bescheid, Grundsicherung, Bürgergeld, Jobcenter, Wohngeld, SGB II/XII …).
Der teure zweite OCR-Durchgang entfällt also im Normalfall (Ausweis erkannt). Für zuverlässiges
Lesen deutscher Bescheide kommt die **deutsche** Tesseract-Sprachdatei ins Image (Dockerfile).

**Sammel-Prüfseite** (ADR 0107): Die Fälle stehen nach Dokumentart getrennt – oben die
**Abweichungen** zum Entscheiden, darunter **unklar** (lohnt einen Blick, mit „Erledigt“) und ganz
unten, eingeklappt, die **Amtsdokumente** (nur zum Nachschlagen; müssen in der Regel nicht angesehen
werden). Der Menü-Zähler zählt nur, was eine Person ansehen sollte (Abweichung + unklar).

**Alt-Anträge**: Schon geprüfte Anträge mit erkanntem Ausweis bekommen ihre Einordnung sofort per
Datenmigration (`0026`, ohne erneutes Lesen). Die ohne erkannten Ausweis bleiben `befund=""` und
werden beim nächsten **„Alle Ausweise prüfen“** eingeordnet: Der Lauf behandelt `befund=""` wie
„noch offen“, liest den Text und setzt die Dokumentart. Das nutzt dieselbe robuste Mechanik wie die
MRZ-Prüfung (eigener Prozess, niedrige Priorität, Zeitlimit je Antrag, fortsetzbar nach einem
Update – ADR 0107/0111). Ein Antrag, an dem der Prüf-Prozess abstürzt, wird terminal als `unklar`
markiert, damit er nicht endlos erneut drankommt.

## Begründung

Die Trennung spart der Tafel viel Handarbeit, ohne je etwas automatisch zu entscheiden: Ein
Amtsdokument wird nur **eingeordnet und einklappt angezeigt**, nicht gelöscht; die unklaren Fälle
bleiben sichtbar. Die Stichwortsuche ist bewusst eine grobe Heuristik auf lokal gelesenem Text –
mehr braucht es für „Bescheid oder nicht“ nicht, und sie verlässt nie den Server. Die Wiedernutzung
des vorhandenen Scan-Laufs (statt einer zweiten Hintergrund-Maschinerie) hält den Code klein und
erbt dessen Absturz-/Update-Robustheit.

## Nachtrag: Einordnung von Hand

Die Stichwortsuche erkennt nicht jeden Bescheid (fremde Vordrucke, schlechte Scans). Deshalb kann
ein Mensch einen unklaren Fall auf der Sammel-Seite selbst einordnen: Neben **„Nichts dran“** (hakt
ab, ohne etwas am Antrag zu ändern) steht bei unklaren Fällen **„Ist ein Bescheid“** – es setzt den
Befund auf `amtsdokument` und hakt den Fall ab (`ausweis_entscheiden`, Aktion `amtsdokument`). So
landet auch ein nicht automatisch erkannter Bescheid mit einem Klick bei den Amtsdokumenten, statt
die unklare Liste zu belasten. Es bleibt eine reine Einordnung durch den Menschen; am Antrag selbst
ändert sich nichts.

## Nachtrag: Bescheid auch von der Antragsseite

Nicht jeder Bescheid landet in der unklaren Liste – manche werden als Ausweis mit abweichender
Staatsangehörigkeit erkannt. Deshalb steht der Hinweis-Banner auf der **Antragsseite** jetzt neben
„Im Antrag übernehmen“ auch **„Ist ein Bescheid, kein Ausweis“** (`ausweis_als_bescheid`): Er setzt
den Befund auf `amtsdokument`, hakt den Fall ab und räumt den Hinweis weg – so lässt sich ein
Bescheid auch beim Durchsehen eines einzelnen Antrags einordnen, nicht nur auf der Sammel-Seite.
