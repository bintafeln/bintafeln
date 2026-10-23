# bintafeln – Projektkontext für Claude Code

Diese Datei beschreibt Ziel, Entscheidungen und Arbeitsregeln des Projekts. Sie wird zu Beginn
jeder Sitzung gelesen und bei grundlegenden Entscheidungen fortgeschrieben (immer per Pull Request).

## Ziel

bintafeln ist eine freie Verwaltungssoftware für Tafeln (Lebensmittelausgaben). Jede Tafel
betreibt ihre eigene Installation auf eigener Infrastruktur: einem kleinen VPS bei einem Hoster
oder einer VM im eigenen Netz. Das Projekt soll über viele Jahre wartbar bleiben und später in die
gemeinsame Verantwortung der nutzenden Tafeln übergehen.

## Getroffene Entscheidungen

- **Lizenz:** AGPL-3.0.
- **Träger:** zunächst der Maintainer privat; GitHub-Organisation `bintafeln`, damit weitere
  Besitzer hinzukommen können.
- **Repository:** vorerst privat; öffentlich, sobald das Grundgerüst stabil ist. Deshalb gilt
  schon jetzt: alles im Repository muss veröffentlichungsfähig sein.
- **Technik:** Python, Django (aktuelle LTS), PostgreSQL, Auslieferung per Docker Compose
  (`app`, `db`, `proxy` mit Caddy).
- **Oberfläche:** serverseitig gerendert mit Django-Templates und HTMX, kein separates
  JavaScript-Framework.
- **Sprache der Oberfläche:** Deutsch, mobilfreundlich.
- **Betrieb:** eine Installation je Tafel, keine Mandantenlogik im Code.
- **Entwicklungsumgebung:** Debian-13-VM mit Docker als „Dummy-Tafel“, Zugriff per `http://IP`
  im Entwicklungsmodus ohne TLS.

## Grundregeln für jeden Beitrag

- Keine festen Werte im Code: keine IP-Adressen, Hostnamen, Pfade, Tafel-Namen oder Logos.
  Konfiguration kommt aus `.env` (Vorlage `.env.example`) oder aus den Einstellungen in der
  Datenbank.
- Niemals echte Personendaten, Passwörter, Schlüssel oder Tokens ins Repository, auch nicht
  vorübergehend. Tests und Beispiele verwenden ausschließlich erfundene Daten.
- Installation mit einem Befehl (`docker compose up -d`), Update mit einem Befehl; Migrationen
  laufen beim Start automatisch und müssen von jeder älteren Version aus funktionieren.
- Keine Migration löscht Daten ohne vorherige Sicherung.
- Wenige, etablierte Abhängigkeiten mit festen Versionen.
- Jede Änderung in einem eigenen Branch und als Pull Request; nie direkt auf `main`.
- Tests (pytest) und Linter (ruff) müssen grün sein.
- Kleine Pull Requests mit einer klaren Aufgabe.
- Vor größeren Änderungen erst einen kurzen Plan vorschlagen und auf Bestätigung warten.
- Änderungen, die Verhalten oder Installation betreffen, aktualisieren die Dokumentation im
  selben Pull Request.
- Grundlegende Entscheidungen werden als kurze ADR in `docs/adr/` festgehalten
  (Problem, Entscheidung, Begründung).

## Datenschutz als Fundament

Kundendaten von Tafeln sind besonders schützenswert. Deshalb von Anfang an:

- Rollen und Rechte je Modul (Admin, Büro, Ausgabe, Kiosk)
- Zwei-Faktor-Anmeldung
- Änderungsprotokoll (wer hat wann was geändert)
- Löschfristen je Datenart mit automatischer Löschung oder Anonymisierung
- Datensparsamkeit (optionale Felder je Tafel abschaltbar)
- Auskunftsexport aller Daten zu einer Person
- verschlüsselte Sicherungen
- TLS im Produktivbetrieb erzwungen

## Module (geplant, in dieser Reihenfolge)

1. **Grundgerüst:** Anmeldung, Rollen, Einstellungen je Tafel, Änderungsprotokoll, Sicherung, CI,
   Installationsanleitung. *Stand: erste Version läuft.*
2. **Kundenstamm:** Personen, Haushalte, Kundennummern, Status, Nachweise mit Ablaufdatum,
   Historie. Import über ein offen dokumentiertes, neutrales CSV-Format mit Prüfbericht.
3. **Neuanmeldung und Warteliste.**
4. **Ausgabe:** Ausgabestellen, Kundennummernvergabe, Kiosk-Ansicht (Scanner arbeitet als
   Tastatur im Browserfeld).
5. **Spenden, Mitglieder, Adressen, Serienbriefe.**
6. **Statistik und Exporte.**

Drucken erfolgt ausschließlich über erzeugte PDFs.

## Wichtige Festlegung zum Kundenstamm

In der ersten Ausbaustufe ist der Kundenstamm ein Snapshot aus einem Altsystem: Jeder Import
ersetzt den Bestand vollständig, im neuen System wird er nur gelesen, nicht bearbeitet. Der Import
wird deshalb als wiederholbarer Vollaustausch gebaut, nicht als Synchronisation einzelner
Datensätze. Erst beim späteren Umstieg zu einem Stichtag übernimmt bintafeln die Führung der Daten.

bintafeln kennt nur das eigene, neutrale Importformat. Werkzeuge, die Daten aus bestimmten
Altsystemen in dieses Format bringen, gehören nicht in dieses Repository.

## Zusammenarbeit

Der Maintainer prüft und mergt jeden Pull Request selbst und spielt ihn auf der Dummy-Tafel ein.
Erklärungen in Pull Requests auf Deutsch und so, dass man die Änderung ohne tiefe
Django-Kenntnisse nachvollziehen kann: was wurde geändert, warum, wie testet man es.

## Technische Kurzreferenz

```bash
.venv/bin/pip install -r requirements-dev.txt   # Entwicklungsumgebung
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest                                # braucht PostgreSQL, siehe README
```

- Projektpaket `bintafeln/` (Einstellungen lesen alles aus Umgebungsvariablen,
  Hilfsfunktionen in `bintafeln/umgebung.py`; Tests nutzen `bintafeln/settings_test.py`).
- Apps unter `apps/`: `core` (Tafel-Einstellungen, Einrichtung, Protokoll),
  `konten` (Benutzermodell `konten.Benutzer`, Rollen in `apps/konten/rollen.py`, Anmeldung).
- Zugriffsschutz für Ansichten: `@rolle_erforderlich(rollen.BUERO, …)` aus `apps.konten.rollen`.
- Neue Modelle mit Personen- oder Stammdaten bei django-auditlog registrieren
  (`auditlog.register(...)`), Geheimnisse und Passwörter mit `exclude_fields` ausnehmen.
- Betriebsmodus: `BINTAFELN_DOMAIN` leer = Entwicklung (http), gesetzt = Produktion (TLS).
