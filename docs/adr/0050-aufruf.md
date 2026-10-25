# 0050: Aufruf – Kundennummern aufrufen, Monitor und Kiosk

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Bisher lief neben bintafeln ein eigenes Aufrufsystem (Flask). Es lud jeden Morgen Listen der
Kundengruppen von einem Fremdsystem herunter, hielt den Stand in JSON-Dateien und hatte eigene
Passwörter. Kunden, die am Einlass schon eingelassen waren (z. B. mit einer Ausnahme vorgezogen),
standen weiter in der Warteschlange.

## Entscheidung

- Modul `aufruf` (ADR 0049). Die Reihenfolge kommt direkt aus dem Kundenstamm: aktive Haushalte
  der Kundengruppen, die heute an der Ausgabestelle dran sind, Gruppen nach Uhrzeit, in der
  Gruppe zufällig gemischt; Haushalte mit Vorrang (ein wählbares Ja/Nein-Zusatzfeld, z. B.
  Schwerbehinderung) zuerst. Kein Download, kein Datentransfer.
- Der Stand eines Tages liegt als JSON in `AufrufTag` (nur Kundennummern), geändert nur in einer
  Transaktion mit gesperrter Zeile (`apps/aufruf/ablauf.py`). Gelöscht nach 4 Wochen, nicht in der
  Datensicherung.
- Laufender Abgleich mit dem Kundenstamm (beim Weiterschalten und höchstens alle 20 Sekunden beim
  Anzeigen): neue Haushalte fair einsortiert (mit Vorrang hinter die wartenden mit Vorrang, die
  übrigen an zufällige Plätze, nie vor die gerade aufgerufenen), entfernte heraus. Wer heute schon
  eine Abholung hat, fällt aus der Warteschlange (abschaltbar).
- Die Seiten des bisherigen Systems (Monitor mit Info-Wechsel und Layout-Einstellung,
  Nummern-Anzeige, Handy-Steuerung, Steuerung, Kiosk mit zweisprachiger Antwort, Abfrage) sind
  im Aussehen unverändert übernommen; ihre Skripte bekommen die Antworten im bisherigen Format.
  Feste Werte (Name, Anschrift, Wetter-Ort) kommen aus den Einstellungen.
- Steuerung mit Anmeldung und Recht `aufruf.steuern` (Zuordnung zu Ausgabestellen gilt);
  Einstellungen mit `einstellungen.aufruf`. Die Geräte im Wartebereich brauchen keine Anmeldung,
  sondern einen geheimen Link je Ausgabestelle, der sich neu erzeugen lässt.
- Infos für den Monitor (Text, Bild, PDF, Webseite) als `AufrufInfo`; Dateien liefert bintafeln
  nur mit gültigem Link aus.

- Ergänzung: Module können Hinweise für die Einlass-Karte liefern (`Modul.einlass`). Der Aufruf
  zeigt dort, ob und wann die Nummer aufgerufen wurde, „Zu spät“ ab `zu_spaet_minuten` nach dem
  Aufruf oder wie viele Nummern noch davor sind. Die Ampel bleibt davon unberührt.

## Begründung

Alles in einem Programm spart den täglichen Download und seine Fehlerquellen, nutzt immer den
aktuellen Kundenstamm und verbindet Einlass und Aufruf. Die gewohnten Bildschirme bleiben, damit
Team und Kunden nicht umlernen müssen. Der Link mit Schlüssel ist für Monitore und Kiosk-Geräte
praktikabel und lässt sich jederzeit sperren; die Geräte zeigen nur Kundennummern.
