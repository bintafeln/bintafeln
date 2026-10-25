# 0043: Update aus der Oberfläche

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Ein Update ging nur mit `./betrieb update` auf dem Server. Tafeln ohne IT-Kenntnisse wollen es in
bintafeln starten. Das Programm läuft aber in einem Container, den das Update selbst ersetzt, und
die Weboberfläche darf keine Kontrolle über Docker bekommen: Wer Docker steuert, ist Root auf dem
Server, und eine Lücke in der Weboberfläche wäre dann eine Übernahme des Servers. Eine
Einrichtung auf dem Server (Systemdienst o. Ä.) ist für die Tafeln keine Option.

## Entscheidung

- Neuer Dienst `updater` in `docker-compose.yml` (Image aus `docker:28-cli` mit bash). Nur er
  bekommt `/var/run/docker.sock` und den Projektordner; er hat keine Ports.
- bintafeln und der Dienst tauschen nur Dateien im Volume `betrieb` aus
  (`/app/data/betrieb`): Lebenszeichen, Versionen mit Änderungen, Status, Protokoll vom Dienst;
  `auftrag.txt` (Version, wer) und `abrufen.txt` von bintafeln.
- Der Dienst nimmt nur Versionen an, die als Tag der Form `JJJJ.M.N` existieren, und startet
  dafür einen eigenen Container mit dem Projektordner unter demselben Pfad wie auf dem Server.
  Der führt `./betrieb update VERSION` aus (Sicherung vorher, Migrationen auch rückwärts) – nötig,
  weil das Update den Dienst selbst neu startet.
- `git fetch` und das Update laufen nicht als root, sondern mit Benutzer- und Gruppennummer des
  Projektordners, dessen Home-Ordner (nur lesend, aus `/etc/passwd` des Servers) und der
  Docker-Gruppe. So greifen die SSH-Schlüssel, `known_hosts` und git-Einstellungen, mit denen
  der Ordner eingerichtet wurde, und alle Dateien behalten ihren Besitzer. (Erste Fassung lief
  als root und scheiterte bei SSH-Remotes mit „Host key verification failed“.)
- Seite „Einstellungen → Update“ mit neuem Recht `system.update` (Vorgabe Admin), Bestätigung,
  Fortschritt, Ergebnis und Protokoll; in der Demo gesperrt.
- Der Dienst kommt einmalig mit dem nächsten `./betrieb update` auf die Server.

## Begründung

Das Restrisiko (wer den Dienst übernimmt, ist Root auf dem Server) ist bewusst in Kauf genommen
und mit dem Maintainer abgestimmt: Der Dienst ist klein, nicht erreichbar und nimmt nur einen
geprüften Versionsnamen an. Die Weboberfläche selbst bleibt ohne Docker-Rechte. Für das Update
selbst wird der bewährte Ablauf von `./betrieb update` wiederverwendet, statt ihn nachzubauen.
