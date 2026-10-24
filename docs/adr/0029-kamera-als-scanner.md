# 0029: Kamera als Barcode-Scanner am Einlass

- Status: Angenommen
- Datum: 2026-10-24

## Problem

Am PC wird der Ausweis mit einem Handscanner gelesen, der als Tastatur arbeitet. Am Handy soll
zusätzlich die eingebaute Kamera den Barcode lesen können. Browser bringen dafür nicht überall
etwas mit: Chrome auf Android hat `BarcodeDetector`, Safari auf dem iPhone und Firefox nicht.

## Entscheidung

- Knopf „Kamera“ neben dem Feld Kundennummer. Erkannt wird mit dem eingebauten
  `BarcodeDetector`, sonst mit der Bibliothek `barcode-detector` (MIT, auf Basis von zxing-cpp
  als WebAssembly).
- Die Bibliothek liegt mit fester Version unter `static/vendor/barcode-detector` und wird nur
  geladen, wenn sie gebraucht wird. Kein CDN: Die Installation braucht keinen fremden Server,
  und Kundendaten verlassen das Gerät nicht.
- Erkannte Nummer wird ins Feld geschrieben und das Formular wie beim Tippen abgeschickt; die
  Prüfung (führende Nullen usw.) bleibt allein auf dem Server.
- Handscanner (USB/Bluetooth) und Eintippen gehen unverändert immer.

## Begründung

Ein Weg für alle Geräte, ohne App und ohne Zusatzkosten. Rund 1 MB WebAssembly lädt nur, wer
die Kamera auf einem Gerät ohne eingebaute Erkennung nutzt, und dann aus dem Browser-Speicher.
Browser geben die Kamera nur über https frei; das passt zur TLS-Pflicht im Produktivbetrieb.
