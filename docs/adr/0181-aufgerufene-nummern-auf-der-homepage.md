# ADR 0181: Aufgerufene Nummern auf der Homepage der Tafel

## Problem

Kunden sollen während der Ausgabe auf der Homepage der Tafel sehen, welche Kundennummern gerade
aufgerufen werden. Der Link des Monitors eignet sich dafür nicht: Sein Schlüssel öffnet auch
Kiosk, Abfrage und die Aufteilung des Monitors (ADR 0050) und darf deshalb nicht öffentlich
stehen. Außerdem lässt sich bintafeln aus Sicherheitsgründen nicht in fremde Seiten einbetten.

## Entscheidung

- Je Ausgabestelle lässt sich **„Aufgerufene Nummern auf der Homepage zeigen“** einschalten
  (Vorgabe aus). Dann gibt es eine kleine öffentliche Seite `/aufruf/homepage/<schlüssel>/` mit
  einem **eigenen Schlüssel**, der nichts anderes öffnet und sich einzeln neu erzeugen lässt.
- Die Seite zeigt **nur** die gerade aufgerufenen Kundennummern, sonst „Zurzeit keine Ausgabe“
  oder „Ausgabe für heute beendet“. Keine Namen, kein Vorrang-Symbol, nicht wer danach kommt,
  keine Knöpfe. Sie lädt ihren Kasten alle zehn Sekunden neu.
- Sie **liest nur**: kein Abgleich der Warteschlange, kein Schreiben. Der Stand gilt fünf
  Sekunden für alle Besucher (gemeinsamer Cache, ADR 0093).
- **Einbetten** erlaubt nur diese eine Seite, und nur der unter „Adresse der Homepage“
  eingetragenen Adresse (`Content-Security-Policy: frame-ancestors`; mehrere sind möglich,
  etwa für eine Testversion der Homepage); ohne Eintrag gar nicht.
  Alle anderen Seiten bleiben gesperrt.
- Außerhalb der Ausgabe nennt die Seite die **nächste Ausgabe** (Wochentag, Datum, Uhrzeit) und
  zählt in Tagen, Stunden und Minuten herunter, ohne Sekunden. Grundlage sind die Kundengruppen des
  Tages aus `ausgabetag.gruppen_am()` (auch Sonderausgaben, ADR 0072) mit der frühesten Uhrzeit
  aus `ausgabetag.beginn()`; Schließzeiten (ADR 0144) werden übersprungen, gesucht wird 14 Tage
  voraus (`homepage.naechste_ausgabe()`). Heute zählt bis eine Stunde nach dem Beginn, falls der
  Aufruf später startet. Der Server rechnet den Text vor (`homepage.countdown()`), der Browser
  zählt mit demselben Text weiter (`static/js/aufruf_homepage.js`).
- Logik in `apps/aufruf/homepage.py`, Ansicht in `views_homepage.py`.

## Begründung

Kundennummern stehen schon auf dem Monitor vor der Tür; mehr als dort zeigt die Homepage nicht,
eher weniger. Der getrennte Schlüssel hält das Risiko klein: Wer ihn kennt, kann nur lesen, was
ohnehin öffentlich hängt. Dass die Seite nichts schreibt und kurz zwischenspeichert, schützt die
Ausgabe vor vielen gleichzeitigen Besuchern. Die Homepage selbst gehört nicht zu bintafeln; sie
bindet die Seite mit einem `<iframe>` ein.
