# 0008: Sicherung und Update

- Status: Angenommen
- Datum: 2026-10-23

## Problem

Jede Tafel betreibt ihre eigene Installation (ADR 0002), meist ohne eigene IT-Abteilung.
Sicherungen müssen deshalb ohne Einrichtung auf dem Server laufen, Kundendaten dürfen dabei nie
unverschlüsselt auf der Platte landen, und ein Update darf keine Daten gefährden.

## Entscheidung

- **Ein vierter Dienst `backup`** in Docker Compose (neben `app`, `db`, `proxy`). Er basiert auf
  demselben PostgreSQL-Image wie `db` und sichert täglich zur Uhrzeit aus `.env`.
- **Verschlüsselung mit age und einem Schlüsselpaar.** Auf dem Server liegt nur der öffentliche
  Schlüssel. Der private Schlüssel wird getrennt aufbewahrt und nur zum Wiederherstellen
  gebraucht. `pg_dump` und `tar` schreiben direkt in age, Klartext berührt die Platte nie.
- **Ohne Schlüssel wird nicht gesichert.** Die Installation läuft trotzdem, Admins sehen auf der
  Startseite eine Warnung.
- **Ein Betriebswerkzeug `./betrieb`** für `update`, `sichern`, `wiederherstellen`, `schluessel`
  und `status`. `update` sichert vor jedem Update. `wiederherstellen` sichert vorher den
  aktuellen Stand und ersetzt die Datenbank in einer einzigen Transaktion.
- Ein **Ende-zu-Ende-Test** in CI spielt Sicherung und Wiederherstellung bei jedem Pull Request
  echt durch.

## Begründung

- Ein eigener Dienst braucht keinen Cronjob und keine Pakete auf dem Server: `docker compose up -d`
  bleibt die ganze Installation.
- Beim Schlüsselpaar nützt ein gestohlener Server oder Sicherungsspeicher nichts. Ein Passwort in
  `.env` läge auf demselben Server wie die Sicherungen.
- age ist klein, gut geprüft, einfach zu bedienen und in Alpine Linux als Paket enthalten.
- Die Datei heißt `betrieb` statt `bintafeln`, weil das Verzeichnis `bintafeln/` schon das
  Django-Projekt enthält.

## Folgen

- Geht der private Schlüssel verloren, sind alle damit verschlüsselten Sicherungen unbrauchbar.
  Die Anleitung betont, ihn getrennt und doppelt aufzubewahren.
- Eine Kopie der Sicherungen an einen anderen Ort ist nicht eingebaut. Die README zeigt ein
  Beispiel mit `rsync`, eine eingebaute Lösung kann später folgen.
- Die Wiederherstellung einer Sicherung aus einer älteren Version funktioniert, weil Migrationen
  beim Start nachgezogen werden. Eine Sicherung aus einer **neueren** Version lässt sich nicht in
  eine ältere Installation einspielen.
