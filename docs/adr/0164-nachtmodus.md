# ADR 0164: Nachtmodus – dunkle Oberfläche je Konto

## Problem

Abends und in dunklen Räumen blenden die hellen Flächen. Es gab nur die helle Darstellung.

## Entscheidung

- `Benutzer.darstellung`: „Hell“ (Vorgabe), „Dunkel (Nachtmodus)“ oder „Wie das Gerät“. Gewählt
  wird unter „Mein Konto → Darstellung“ (`konten.views.darstellung`); für niemanden ändert sich
  ungefragt etwas.
- `base.html` setzt bei „Dunkel“ `data-nacht` am `<html>`. Bei „Wie das Gerät“ setzt es
  `static/js/darstellung.js` nach `prefers-color-scheme` – im Kopf der Seite, vor dem ersten
  Zeichnen, damit nichts hell aufblitzt.
- Die dunklen Farben stehen am Ende von `static/css/bintafeln.css` unter `:root[data-nacht]`:
  die Grundvariablen (`--grund`, `--flaeche`, `--text`, `--rand` …) und ein dunkles Gegenstück für
  jede Regel mit fester heller Fläche (derselbe Farbton, mit `color-mix` dunkel getönt).
- Die Farbe der Tafel bleibt der Akzent. Für Links und Text auf dunklem Grund liefert
  `farben.farbtoene()` den hellen Ton `akzent_nacht`; im Nachtmodus ist `--akzent-dunkel` dieser Ton.
- Hell bleiben: PDFs und Ausdrucke, Unterschriftsfelder, Bild- und Ausweisvorschauen, QR-Codes,
  die öffentlichen Seiten und die Aushang-Monitore. Das Hintergrundbild der Tafel wird abgedunkelt.
- Erster Schritt: Grundgerüst und alle Flächen ohne eigene Schriftfarbe. Kleine Markierungen mit
  eigener dunkler Schrift auf hellem Grund (Status-Schilder) bleiben vorerst hell und lesbar; sie
  folgen in einem zweiten Schritt.

## Begründung

Eine Einstellung am Konto gilt auf jedem Gerät und braucht kein Cookie. Ein einziger CSS-Block mit
Variablen hält den Nachtmodus neben der hellen Darstellung wartbar; wer eine neue helle Fläche
anlegt, ergänzt dort das Gegenstück.
