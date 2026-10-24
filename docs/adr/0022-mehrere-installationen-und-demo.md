# 0022: Mehrere Installationen auf einem Server, öffentliche Demo

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0002, ADR 0003

## Problem

Auf einem Server sollen mehrere bintafeln laufen können, z. B. eine Tafel und eine öffentliche
Demo, dazu eine Projektwebseite. Bisher belegte jede Installation mit ihrem eigenen Proxy die
Ports 80 und 443. Eine Demo braucht außerdem erfundene Daten, die sich regelmäßig erneuern.

## Entscheidung

- Es bleibt bei **einer Installation je Tafel** (ADR 0002): eigener Ordner, eigene Datenbank,
  eigene Sicherung. Keine Mandantenlogik.
- Ein **gemeinsamer Proxy** (`docker/gemeinsamer-proxy`, Caddy) belegt die Ports, holt die
  Zertifikate und leitet je Domain an eine Installation weiter. Die Installationen hängen in
  dessen Docker-Netz `bintafeln-web`.
- Eine Installation schaltet das über ihre `.env` ein: `COMPOSE_PROJECT_NAME` (eindeutiger Name)
  und `COMPOSE_FILE` mit `docker/hinter-proxy.yml`. Ihr eigener Caddy bleibt (statische Dateien,
  Sicherheits-Kopfzeilen), belegt aber keine Ports, macht kein TLS und vertraut den
  weitergeleiteten Angaben nur aus privaten Netzen. Ohne diese Zeilen ändert sich nichts.
- Abbilder heißen nach `COMPOSE_PROJECT_NAME`, damit Installationen in verschiedenen Versionen
  sich nicht gegenseitig überschreiben.
- **Demo:** `BINTAFELN_DEMO=true` zeigt einen Hinweis auf jeder Seite und die Demo-Zugänge auf
  der Anmeldeseite (Passwort aus der `.env`, nicht im Code). Passwort ändern, Zwei-Faktor und
  Mailserver sind gesperrt. `manage.py demo_zuruecksetzen` löscht alle Daten und legt die
  erfundenen Beispieldaten aus `docs/beispiele/import` und Demo-Konten an; ohne den Schalter
  verweigert er. Gibt es Konten, die nicht mit `demo-` beginnen, bricht er ebenfalls ab
  (Schutz, falls er versehentlich im Ordner einer echten Installation läuft).

## Begründung

Ein gemeinsamer Proxy ist der übliche Weg, mehrere Dienste unter einer Adresse zu betreiben,
und braucht keine Änderung an der Anwendung. Weil der Umstieg nur die `.env` betrifft, bleibt
die Installation mit einem Befehl erhalten. Die Demo arbeitet mit den ohnehin gepflegten
Beispieldateien und kann echte Daten nicht berühren, weil der Befehl nur im Demo-Betrieb läuft.
