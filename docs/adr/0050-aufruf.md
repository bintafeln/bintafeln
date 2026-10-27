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
  Aufruf oder wie viele Nummern der Kunde zu früh ist. Ist er zu früh oder zu spät, leuchtet die
  Ampel grün und Gelb blinkt dazu (Hinweis mit „ampel“ und „wort“,
  `ampel.modul_hinweise_beachten()`); die Bewertung bleibt „Abholung möglich“ mit „Kunde ist zu
  früh/spät“, Rot bleibt Rot. Bei „Zu spät“ bietet
  der Hinweis einen Knopf „N Nummern verschieben“ (`knopf` im Hinweis, `aufruf:verschieben`), der
  wie „zu spät gekommen“ am Handy neu einsortiert.
- Ergänzung: Nicht jede Ausgabestelle ruft auf: `AufrufEinstellungen.aktiv` je Ausgabestelle
  (Vorgabe an); aus = keine Steuerung, kein Kasten, keine Hinweise am Einlass.
- Ergänzung: Kurz-Steuerung unter dem Menü (`Modul.seitenleiste`, `aufruf:leiste`) für alle mit
  Einlass und Recht „Kunden aufrufen“: aufgerufene Nummern der gewählten Ausgabestelle, „Nächste
  hereinrufen“, Zurück und Starten; lädt per HTMX nach und fragt alle 5 Sekunden neu, sofort nach einer Buchung am Einlass
  (Ereignis `einlassGeaendert` über den Kopf `HX-Trigger`).

## Begründung

Alles in einem Programm spart den täglichen Download und seine Fehlerquellen, nutzt immer den
aktuellen Kundenstamm und verbindet Einlass und Aufruf. Die gewohnten Bildschirme bleiben, damit
Team und Kunden nicht umlernen müssen. Der Link mit Schlüssel ist für Monitore und Kiosk-Geräte
praktikabel und lässt sich jederzeit sperren; die Geräte zeigen nur Kundennummern.

## Nachtrag: zurückgenommene Abholungen (2026-10-25)

Wer als eingelassen aus der Warteschlange genommen wurde und dessen Abholung danach zurückgenommen
wird (Korrekturwunsch, ADR 0035), kommt beim nächsten Abgleich an seinen alten Platz zurück: vor
den ersten damaligen Nachfolger, der noch wartet (`stand["nachfolger"]`). Ist der Platz schon
vorbei, wird er als nächster aufgerufen, nie vor die gerade angezeigten Nummern.

## Nachtrag: am Kiosk gemeldet (2026-10-27)

Scannt ein Kunde am Kiosk seinen Ausweis (Abfrage mit `kiosk=1`, nicht die Abfrage-Seite),
legt `ablauf.kiosk_melden()` eine `KioskMeldung` (Ausgabestelle, Tag, Kundennummer) an; ältere
Tage werden dabei gelöscht, in der Datensicherung sind die Meldungen ausgenommen.
`stand_fuer_anzeige()` liefert dazu `present_flags` (und für „Danach“ und „Letzte“), die Steuerungen
färben gemeldete Nummern grün, die übrigen dunkelrot. Solange sich am Tag niemand gemeldet hat,
bleiben die Flags `None` (Ausgabestellen ohne Kiosk sehen keine roten Nummern). Die öffentliche
Anzeige bekommt die Flags nicht. Am Einlass Eingetragene fallen jetzt auch aus „Danach“ sofort
heraus, nicht erst beim nächsten Abgleich.

## Nachtrag: automatisch weiter (2026-10-27)

Sind alle Nummern von „Bitte eintreten“ schon am Einlass eingetragen, ruft `aktualisieren()` von
selbst „Weiter“ auf (unter Sperre noch einmal geprüft, damit zwei Geräte nicht doppelt
weiterschalten), auch über das Ende einer Kundengruppe hinweg. Der Schritt steht wie ein
manuelles „Weiter“ im Verlauf und lässt sich zurücknehmen. Einstellung `automatisch_weiter`
(Vorgabe an).
