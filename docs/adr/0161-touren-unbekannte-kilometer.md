# ADR 0161: Touren – Kilometer ohne Eintrag im Fahrtenbuch

Ergänzt ADR 0151 (Fahrten und Fahrtenbuch).

## Problem

Bei „Fahrt beginnen“ schlägt bintafeln den letzten bekannten Kilometerstand des Fahrzeugs vor.
Zeigt der Tacho mehr, wurde das Fahrzeug zwischendurch gefahren, ohne dass es eine Fahrt dazu
gibt. Der Fahrer überschreibt den Vorschlag – die Kilometer dazwischen fehlten bisher einfach im
Fahrtenbuch, die Lücke war nur beim Nachrechnen zu sehen.

Außerdem gingen Fahrzeug und Kilometerstand verloren, wenn jemand vor dem Beginn noch eine andere
Seite ansah.

## Entscheidung

- Trägt der Fahrer einen **höheren** Stand ein als bekannt, hält die Fahrt den bekannten Stand
  fest (`Fahrt.km_vorher`). Das Fahrtenbuch zeigt darunter eine Zeile **„unbekannt“** mit beiden
  Ständen und den Kilometern (`Fahrt.km_unbekannt`), auch in der CSV-Datei. Über der Liste werden
  diese Kilometer getrennt von den eingetragenen gezählt.
- Ein gleicher oder kleinerer Stand erzeugt keine Zeile (dann war der Stand am Fahrzeug zu hoch).
- Berichtigt das Büro die Abfahrt auf den bekannten Stand oder darunter, verschwindet die Zeile.
- Die Zeile ist keine eigene Fahrt: keine Tour, keine Besetzung, nichts zu bearbeiten.
- **Fahrzeug und Kilometerstand merkt sich das Gerät** für diese Tour an diesem Tag
  (`static/js/fahrt_km.js`, localStorage), bis die Fahrt begonnen ist.

## Begründung

- Ein Fahrtenbuch soll lückenlos sein; eine sichtbare Lücke ist ehrlicher als eine unsichtbare.
- „Unbekannt“ nennt niemanden: Es wird nicht gezeigt, wer gefahren sein könnte.
- Gemerkt wird im Gerät und nicht auf dem Server, weil bis zum Beginn noch nichts feststeht.
