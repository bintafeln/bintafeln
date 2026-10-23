# 0009: Zwei-Faktor: Selbsteinrichtung, Pflicht je Rolle, Notfallcodes

- Status: Angenommen
- Datum: 2026-10-23
- Ergänzt: ADR 0004

## Problem

ADR 0004 hat die Zwei-Faktor-Anmeldung vorbereitet, aber Geräte konnte nur ein Admin in der
Verwaltung anlegen, und eine Pflicht gab es nicht. Wer Kundendaten sieht, soll Zwei-Faktor
nutzen müssen. Gleichzeitig arbeiten in Tafeln viele Ehrenamtliche, nicht alle mit Smartphone,
und Kiosk-Geräte werden geteilt.

## Entscheidung

- Jede Person richtet die Zwei-Faktor-Anmeldung **unter „Mein Konto“ selbst ein**
  (QR-Code, Bestätigung mit einem Code).
- Nach der Einrichtung gibt es einmalig **10 Notfallcodes**, jeder einmal nutzbar.
- **Pflicht je Rolle**, einstellbar durch Admins in den Tafel-Einstellungen (Datenbank).
  Voreinstellung: **Pflicht für Admin und Büro**, nicht für Ausgabe und Kiosk.
- Eine Middleware setzt die Pflicht durch: Ohne eingerichtetes Gerät ist bei Pflicht-Rollen
  nur die Einrichtung erreichbar. Sitzungen ohne Code-Eingabe werden abgemeldet, sobald es ein
  Gerät gibt.
- Rückweg bei verlorenem Handy: Notfallcode, Zurücksetzen durch einen Admin, als letzter Ausweg
  der Befehl `manage.py zwei_faktor_zuruecksetzen`.
- QR-Codes erzeugt die Bibliothek **segno** serverseitig als SVG.

## Begründung

- Admin und Büro sehen alle Kundendaten, dort lohnt die Pflicht am meisten. In der Ausgabe und
  am Kiosk würde sie Ehrenamtliche ohne Smartphone oder geteilte Geräte aussperren. Jede Tafel
  kann das anders einstellen.
- Notfallcodes vermeiden, dass jedes verlorene Handy zum Admin oder auf die Kommandozeile führt.
- segno hat keine weiteren Abhängigkeiten, ist BSD-lizenziert und braucht kein JavaScript.

## Folgen

- Nach dem Update auf diese Version müssen Admins und Büro-Konten bei der nächsten Aktion
  Zwei-Faktor einrichten.
- Ein Zurücksetzen durch Admins in der eigenen Oberfläche kommt mit der Benutzerverwaltung.
