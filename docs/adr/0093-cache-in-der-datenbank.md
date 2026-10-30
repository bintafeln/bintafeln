# 0093 – Gemeinsamer Cache in der Datenbank

## Problem

Die App läuft im Betrieb mit mehreren gunicorn-Prozessen (Vorgabe 3). Ohne eingestellten Cache
nutzt Django den prozesslokalen Speicher-Cache (LocMemCache): Jeder Prozess hat eigene Zähler,
und bei jedem Neustart oder Update aus der Oberfläche sind sie weg.

Darauf bauen aber Schutzmechanismen, allen voran die **Sperre nach zu vielen Anmeldeversuchen**
(`AnmeldeForm`: 5 Fehlversuche je Benutzername → 15 Minuten gesperrt), außerdem die Drosseln bei
„Passwort vergessen“ und beim Empfang der Verzeichnis-Meldung. Verteilt auf 3 Prozesse griff die
Sperre erst nach rund dreimal so vielen Versuchen und überlebte kein Update – also zu schwach für
einen öffentlich erreichbaren Server.

## Entscheidung

- `CACHES` steht auf Djangos **DatabaseCache** mit der Tabelle `bintafeln_cache`. Der Cache liegt
  damit in PostgreSQL: gemeinsam über alle Prozesse und dauerhaft, auch über Updates hinweg (die
  Datenbank liegt im eigenen `db`-Dienst mit Volume).
- Die Tabelle legt die Migration `core/0022` mit `createcachetable` an. So bleibt es bei
  „Installation und Update mit einem Befehl“; die Migrationen laufen beim Start automatisch.
- Kein zusätzlicher Dienst (z. B. Redis): Die vorhandene Datenbank genügt für diese Last, und das
  Projekt hält die Zahl der Abhängigkeiten klein.
- In Tests wird der schnelle LocMemCache genutzt, damit reine Prüftests keinen Datenbankzugriff
  brauchen; dass der Datenbank-Cache funktioniert, deckt ein eigener Test ab.

## Begründung

Die Schutzzähler müssen über alle Prozesse zählen und ein Update überstehen, sonst sind sie
wirkungslos. Die Datenbank ist dafür schon da und übersteht den Austausch des App-Containers.
