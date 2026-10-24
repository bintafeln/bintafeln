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
  (`app`, `db`, `proxy` mit Caddy, `backup` für die verschlüsselte Sicherung, siehe ADR 0008).
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
- **Eingabefelder: Auswahl statt Freitext.** Wo es feste Werte gibt (z. B. Anrede,
  Führerscheinklassen, Bundesland) oder registrierte Mitarbeitende gemeint sind (z. B. „gesehen
  von“, „eingetragen von“), immer ein Auswahlmenü anbieten; Mehrfachauswahl, wo mehrere Werte
  möglich sind. Sinnvoll vorbelegen (z. B. mit der angemeldeten Person). Listen zentral in
  `apps/core/auswahl.py`; gespeicherte Werte, die nicht mehr in der Liste stehen, bleiben
  wählbar.
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
Ausnahme: Der Empfang trägt Abholungen und Ausnahmen ein; der nächste Import ersetzt sie
(ADR 0013).

bintafeln kennt nur das eigene, neutrale Importformat. Werkzeuge, die Daten aus bestimmten
Altsystemen in dieses Format bringen, gehören nicht in dieses Repository.

Fachliche Anforderungen an die Module 2 bis 4 stehen in `docs/fachkonzept.md`, das Importformat
in `docs/importformat.md` (verbindlich für den Import; Änderungen nur per PR mit Versionshinweis).

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
  `konten` (Benutzermodell `konten.Benutzer`, Rollen in `apps/konten/rollen.py`, Anmeldung),
  `kunden` (Kundenstamm; Werte-Parser für den Import in `apps/kunden/werte.py`, Zusatzfeld-Werte
  als JSON in `Haushalt.zusatz` bzw. `Person.zusatz`, Schlüssel = `Zusatzfeld.schluessel`).
  Import in `apps/kunden/importieren.py`: `pruefen()` (Bericht ohne Inhalte) und `uebernehmen()`
  (Vollaustausch in einer Transaktion, Auditlog nur für den `ImportLauf`). Löschfristen
  (Abholungen, Ausnahmen, Zugriffsprotokoll) wendet `fristen_anwenden()` in
  `apps/kunden/models.py` an (ADR 0011, 0012). Jeder Aufruf der Detailseite eines Haushalts
  schreibt einen `Zugriff`. Neue Spalten im Importformat brauchen Doku,
  Beispieldatei und Test in `tests/test_kunden_import.py`.
  `ausgabe` (Empfang; Ampel-Regeln als reine Funktion in `apps/ausgabe/ampel.py`,
  Einstellungen in `AusgabeEinstellungen`; Kundenkonto nur über `apps/ausgabe/konto.py`
  buchen, nie `Haushalt.kontostand` direkt ändern, ADR 0014; Kasse-Auswertung in
  `apps/ausgabe/kasse.py`).
- Statische Dateien laufen im Betrieb über `ManifestStaticFilesStorage` (Dateinamen mit
  Prüfsumme), weil Caddy sie einen Tag zwischenspeichern lässt. Tests nutzen die einfache
  Ablage.
- Zugriffsschutz für Ansichten: `@rolle_erforderlich(rollen.BUERO, …)` aus `apps.konten.rollen`.
- Mitarbeitende: Logik und Schutzregeln in `apps/konten/verwaltung.py` (nie löschen, nur
  sperren; ADR 0015). `Benutzer.passwort_aendern` erzwingt über
  `PasswortAendernMiddleware` ein neues Passwort, bevor die Zwei-Faktor-Einrichtung kommt.
  Stammdaten, Wiedervorlagen, Führerschein-Kopie und Löschfrist in `apps/konten/personal.py`
  (ADR 0017). App `personal` (Rolle Personal): Verträge, Abwesenheiten, Stunden; Rechenregeln
  in `apps/personal/berechnung.py` (ADR 0018). Verschlüsselte Dateien nur über
  `apps.core.privatdateien`.
- Mails nur über `apps.core.mail.senden()` (Mailserver aus der Datenbank, verständliche
  `MailFehler`). Geheimnisse in der Datenbank nur über `apps.core.geheimnis` verschlüsselt
  speichern (ADR 0016). In Tests landen Mails in `django.core.mail.outbox`.
- Zwei-Faktor: Logik in `apps/konten/zwei_faktor.py`, Durchsetzung in
  `apps.konten.middleware.ZweiFaktorMiddleware`. In Tests Benutzer mit der Fixture `anmelden`
  anmelden (verifizierte Sitzung); ein bloßes `force_login` landet bei Pflicht-Rollen auf der
  Einrichtungsseite.
- Neue Modelle mit Personen- oder Stammdaten bei django-auditlog registrieren
  (`auditlog.register(...)`), Geheimnisse und Passwörter mit `exclude_fields` ausnehmen.
- Betriebsmodus: `BINTAFELN_DOMAIN` leer = Entwicklung (http), gesetzt = Produktion (TLS).
- Betrieb auf dem Server über `./betrieb` (update, sichern, wiederherstellen, schluessel, status).
  Sicherungsskript im Dienst `backup`: `docker/backup/sicherung.sh`.
- Shell-Skripte müssen `shellcheck` bestehen. Änderungen an Sicherung oder Wiederherstellung
  deckt `tests/sicherung_e2e.sh` ab (läuft in CI im Job `docker`).
