# 0049: Zuschaltbare Module

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Viele Tafeln haben eigene kleine Programme neben dem Kundenstamm (Aufrufsystem, Wartelisten,
Wochenübersicht, Spendenbelege …). Sie sollen in bintafeln aufgehen. Nicht jede Tafel braucht sie
aber; wer sie nicht nutzt, soll sie nirgends sehen, und der übrige Code soll nicht mit
Sonderfällen für jedes dieser Programme gefüllt werden.

## Entscheidung

- Jedes solche Programm wird ein **Modul**: eine eigene App unter `apps/` mit einer Datei
  `modul.py`, die ein `Modul` (`apps/core/module.py`) beschreibt: Kennung, Titel, Adressen,
  Rechte mit Vorgaben für die mitgelieferten Rollen, Handbuch-Kapitel (Vorlage in der App),
  Menüeinträge und den Bereich für die Datensicherung.
- `settings.BINTAFELN_MODULE` listet die installierten Module; sie stehen in `INSTALLED_APPS`,
  ihre Migrationen laufen immer (Updates und Sicherungen bleiben gleich).
- Jede Tafel schaltet Module in **Einstellungen → Tafel → Zusätzliche Module** ein
  (`TafelEinstellungen.module`, Vorgabe: aus).
- Ausgeschaltet heißt: keine Menüeinträge, keine Hilfe-Kapitel, keine Rechte in der
  Rollenverwaltung (gespeicherte Rechte bleiben unverändert) und keine Seiten – die
  `ModulMiddleware` beantwortet die Adressen mit 404. Die Daten bleiben erhalten.
- Rechtekatalog, Menü, Handbuch, Datensicherung und URLs sammeln die Beiträge der Module ein;
  dort steht kein modulspezifischer Code. Rechte für bestehende Rollen vergibt eine
  Datenmigration im Modul selbst.

## Begründung

So bleibt der Kern schlank und jedes Modul an einem Ort. Eine Tafel kann ein Modul ausprobieren
und wieder abschalten, ohne Daten zu verlieren. Neue Module folgen einem festen Muster.
