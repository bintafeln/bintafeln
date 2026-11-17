# 0141 – Druckansicht für PDFs auf Tablets im Kiosk-Modus

## Problem

Viele Ausgabestellen betreiben ihr Tablet im Kiosk-Modus. Ein PDF (z. B. „Kassenabschluss drucken
(PDF)“) öffnet dort im eingebauten Betrachter ohne Knopf zum Drucken und ohne Weg zurück; man
kommt aus dem PDF nicht mehr heraus. Ein PDF in eine Seite einzubetten hilft nicht: Das iPad zeigt
eingebettete PDFs oft nur mit der ersten Seite, und Drucken aus dem eingebetteten PDF klappt nicht
zuverlässig.

## Entscheidung

- `apps.core.druckansicht.DruckansichtMiddleware` fängt jedes PDF ab, das als Seite geöffnet wird
  (GET, `Content-Type: application/pdf`, nicht als Download, nicht eingebettet), wenn die
  Druckansicht auf dem Gerät gilt. Statt des PDFs kommt eine normale Seite: jede PDF-Seite als
  Bild (pypdfium2, keine neue Abhängigkeit), darüber „Drucken“ (`window.print()`, beim Drucken
  nur die Seiten), „PDF herunterladen“, „Zurück“ und „Per E-Mail senden“.
- Kein PDF muss dafür geändert werden; alle PDFs aller Module bekommen die Druckansicht.
  PDFs mit mehr als 30 Seiten (z. B. Serienbriefe) öffnen weiter direkt.
- Wann sie gilt: Vorgabe für Konten einer Ausgabestelle (ADR 0059), sonst je Gerät unter „Mein
  Konto → PDFs auf diesem Gerät“ (Cookie, gilt nur für diesen Browser, in beide Richtungen
  schaltbar). `?_pdf=roh` liefert immer das PDF selbst.
- Gespeichert wird nichts. Die Seite enthält das PDF; zum Mailen schickt der Browser es mit einer
  Signatur der Prüfsumme zurück, sodass nur unverändert von bintafeln erzeugte PDFs verschickt
  werden. Empfänger nur zur Auswahl: E-Mail der gewählten Ausgabestelle, die eigene (persönliche
  Konten) oder die der Tafel. Die Mail läuft über `mail.senden()` (Art „druck“, Archiv).

## Begründung

Eine eigene Seite mit Bildern druckt auf jedem Gerät über den normalen Druckdialog, auch im
Kiosk-Modus, und hat immer einen Weg zurück. Die Umsetzung an einer Stelle (Middleware) erfasst
alle vorhandenen und künftigen PDFs, ohne jede Ansicht anzufassen. Die Wahl je Gerät passt dazu,
dass dieselbe Person am PC das PDF direkt, am Tablet die Druckansicht braucht.

## Nachtrag: PDF im Fenster über der Seite (App vom Home-Bildschirm)

Im Einsatz zeigte sich: In der App vom Home-Bildschirm (Vollbild, keine Browserleiste) öffnet
jedes PDF in einem eigenen Fenster, aus dem man nicht zurückkommt („PDF öffnen“ blieb schwarz),
und `window.print()` tut dort nichts. Deshalb:

- `static/js/pdf_fenster.js` holt PDFs (Links mit `target="_blank"` auf eigene Seiten, GET- und
  POST-Formulare über `neues_fenster.js`) im Hintergrund und zeigt sie in einem Fenster über der
  Seite (`<dialog>`): Vorschau aller Seiten (`core:druck_vorschau`), „Drucken“, „Sichern“,
  „Per E-Mail“ und ein großes „Schließen“. Die Seite wird nie verlassen.
- „Drucken“ teilt das PDF über das Teilen-Menü des Geräts (Web Share mit Datei); dort steht
  „Drucken“ (AirPrint). Ohne Teilen-Menü der Druckdialog über einen unsichtbaren Rahmen.
- Aktiv in der App (`display-mode: standalone/fullscreen`, `navigator.standalone`) und auf
  Geräten mit Druckansicht (`<body data-pdf-fenster="1">`). Signatur und Dateiname kommen beim
  Abholen (`X-Bintafeln-Pdf`) als Kopfzeilen der Antwort, Vorschau und Mail nehmen das PDF als
  Datei mit dieser Signatur.
- Die Druckansicht als Seite bleibt für PDFs, die direkt als Seite geöffnet werden; auch dort
  teilt „Drucken“ das PDF, wenn das Gerät es kann.
