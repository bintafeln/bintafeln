# ADR 0105: Hochgeladene Nachweise bei einem Formularfehler behalten

## Problem

Füllt jemand den Online-Antrag aus, lädt Nachweise hoch und vergisst ein Pflichtfeld, erscheint
das Formular mit roter Markierung erneut – aber die schon ausgewählten Dateien sind weg. Grund:
Browser dürfen ein Datei-Feld aus Sicherheitsgründen nicht serverseitig wieder befüllen; beim
Neuladen der Seite ist die Auswahl verloren. Die Antragstellenden müssen jede Datei erneut
auswählen, nur weil ein anderes Feld fehlte.

## Entscheidung

Zwei Maßnahmen, die zusammenwirken:

1. **Der Browser prüft Pflichtfelder vor dem Absenden.** Am Formular steht kein `novalidate` mehr,
   also meldet der Browser ein fehlendes Pflichtfeld sofort, ohne die Seite neu zu laden – die
   ausgewählten Dateien bleiben im Feld. Die serverseitige Prüfung bleibt die maßgebliche; sie
   fängt alles ab, was der Browser nicht prüft.

2. **Der Server behält hochgeladene Nachweise über einen Fehler hinweg.** Beim Absenden werden die
   Dateien sofort verschlüsselt als `AntragEntwurfNachweis` abgelegt und an die Sitzung gebunden
   (`apps/antraege/nachweise.py`). Schlägt die Prüfung an einem anderen Feld fehl, zeigt das
   Formular sie wieder an („Bereits hochgeladen …“) mit der Möglichkeit, einzelne wieder
   wegzunehmen. Beim erfolgreichen Absenden werden daraus die `AntragAnhang` des Antrags. Das
   Formular selbst verarbeitet keine Dateien mehr; das macht die Ansicht über
   `nachweise`.

Liegen gebliebene Entwürfe (abgebrochene Anträge) löscht `models.fristen_anwenden` nach einem Tag
samt Dateien; die Entwürfe sind von der Datensicherung ausgenommen (vorübergehende Daten).

## Begründung

- Datei-Felder lassen sich nicht wieder befüllen – das Behalten muss serverseitig geschehen, damit
  es in **allen** Fehlerfällen greift (nicht nur bei fehlenden Pflichtfeldern), auch ohne
  JavaScript.
- Die Browser-Prüfung erspart im häufigsten Fall (ein vergessenes Pflichtfeld) das Neuladen ganz.
- Nachweise sind sensibel: Sie liegen nur kurz, verschlüsselt und an die Sitzung gebunden, und
  werden nach einem Tag automatisch gelöscht (Datenschutz-Grundsatz der automatischen Löschfristen).
