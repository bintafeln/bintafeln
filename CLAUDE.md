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
  (`app`, `db`, `proxy` mit Caddy, `backup` für die verschlüsselte Sicherung, siehe ADR 0008,
  `updater` für das Update aus der Oberfläche, ADR 0043).
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
- **Begriffe in der Oberfläche und Doku:** „Einlass“ (nicht „Empfang“), „Anmerkung“ (nicht
  „Bemerkung“), „Notiz“ für Notizen (nicht „Hinweis“). Namen im Code und im Importformat
  (`empfang`, `bemerkung`, `bemerkungen.csv`) bleiben, damit URLs, Migrationen und Importdateien
  stabil bleiben.
- Grundlegende Entscheidungen werden als kurze ADR in `docs/adr/` festgehalten
  (Problem, Entscheidung, Begründung).

## Datenschutz als Fundament

Kundendaten von Tafeln sind besonders schützenswert. Deshalb von Anfang an:

- Rollen frei anlegbar, fein einstellbare Rechte je Rolle (ADR 0033)
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
Ausnahmen: Der Einlass trägt Abholungen und Ausnahmen ein (ADR 0013), der Admin kann den
Kundenstamm bearbeiten (ADR 0025), und Anträge werden mit dem Aufnahme-Assistenten in den
Kundenstamm aufgenommen (ADR 0028). Der Import zeigt vorher einen Abgleich; in bintafeln
geänderte oder aufgenommene Haushalte lassen sich dabei je Haushalt behalten. Statt des
Vollaustauschs kann ein Import auch nur ergänzen oder aktualisieren, mit Wahl je Feld (ADR 0078).
Einen festen Stichtag gibt es nicht: Irgendwann wird einmal alles übernommen, ab dann gilt dieser Stand.

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
  Beispieldatei und Test in `tests/test_kunden_import.py`. Bearbeiten durch den Admin in
  `views_bearbeiten.py`/`forms_bearbeiten.py`; jede Änderung setzt `Haushalt.geaendert_am`.
  Notizen (`Notiz`, ADR 0026) hängen an der Kundennummer und überstehen den Import; die Rolle
  Ausgabe sieht nur die Angaben aus ADR 0026.
  Dokumente zum Haushalt (`HaushaltDokument`, ADR 0030) ebenfalls an der Kundennummer,
  verschlüsselt über `apps.core.privatdateien`, Frist je `Dokumentart`, Ansichten in
  `views_dokumente.py`.
  Historie (`HaushaltEreignis`, ADR 0031) über `apps/kunden/historie.py`: Schnappschuss vor und
  nach jeder Änderung am Kundenstamm (`festhalten()`, beim Import `import_festhalten()`).
  Ohne gültigen Ausweis keine Kundengruppe (ADR 0061): `apps/kunden/gruppen.py` (`pruefen()` nach
  jeder Änderung, `regel_anwenden()` täglich und beim Import), Zeiten in `Gruppenzeit`.
  `ausgabe` (Einlass; Beitrag über `AusgabeEinstellungen.beitrag_fuer()` – zahlende Personen
  ab Alter × Betrag, Zusatzbeiträge optional, `BeitragsfreierZeitraum`;
  Ampel-Regeln als reine Funktion in `apps/ausgabe/ampel.py`,
  Einstellungen in `AusgabeEinstellungen`; Kundenkonto nur über `apps/ausgabe/konto.py`
  buchen, nie `Haushalt.kontostand` direkt ändern, ADR 0014; Kasse-Auswertung in
  `apps/ausgabe/kasse.py`; Kamera-Scanner `static/js/kamera_scanner.js` für Felder mit
  `data-kamera`, Bibliothek fest unter `static/vendor/barcode-detector`, kein CDN, ADR 0029;
  Sonderaktionen: Regeln in `apps/ausgabe/sonderaktionen.py`, `Teilnahme` an der Kundennummer,
  ADR 0032; aktuelle Ausgabestelle nur über `apps/ausgabe/stelle.py` (`aktuelle()`, Auswahl oben
  im Menü, `Benutzer.gewaehlte_stelle`, Fortschritt in der Kopfzeile, ADR 0067); wer an einem
  Tag dran ist (auch Sonderausgaben) nur über `apps/ausgabe/ausgabetag.py` (ADR 0072).
  Merkmale (Ja/Nein-Zusatzfelder am Einlass und auf dem Ausweis) in `apps/kunden/merkmale.py`,
  mitgelieferte in `FESTE_MERKMALE` (ADR 0071).
  Sammel-Verlängerung der Ausweise: Regeln in `apps/kunden/verlaengerung.py`, Bedingungen in
  `KundenEinstellungen.verlaengern_*`, Anliegen der `Nachricht` in `apps/core/auswahl.py` (ADR 0068).
  Krankmeldung eines Kunden: `Notiz` mit `krank_von/bis/grund`, Logik in `apps/kunden/krankmeldung.py`,
  zuschaltbar, nach dem Ende gelöscht (ADR 0075).
  Notizen an die Ausgabestelle (`Notiz.an_stelle`, Startseite, Antwort beim Ausweisdruck) in
  `apps/kunden/an_stelle.py`; feste Notiz-Vorlagen zu `FESTE_ANLIEGEN` (ADR 0070).
- Statische Dateien laufen im Betrieb über `ManifestStaticFilesStorage` (Dateinamen mit
  Prüfsumme), weil Caddy sie einen Tag zwischenspeichern lässt. Tests nutzen die einfache
  Ablage.
- Zugriffsschutz nur über Rechte, nie Rollennamen (ADR 0033): Ansichten mit
  `@rollen.recht_erforderlich("kunden.liste")`, im Code `rollen.hat_recht(...)`, in Templates
  `{% if "kunden.kontakt" in rechte %}`. Katalog und Vorgaben der mitgelieferten Rollen in
  `apps/konten/rechte.py`; neue Rechte dort ergänzen und per Datenmigration bestehenden Rollen
  geben. Rolle Admin hat immer alle Rechte. In Tests: Fixture `recht_geben`.
  `tests/test_zugriffsschutz.py` prüft alle Adressen (ADR 0065): öffentliche Seiten und Seiten
  für alle Angemeldeten dort eintragen; Rechte immer vor der Suche nach dem Datensatz prüfen.
- Einzelne Haushalte nur über `apps.kunden.zugang.haushalt(request.user, kundennummer)` laden
  (prüft die Zuordnung zu Ausgabestellen, ADR 0034); Listen mit `zugang.filtern()`.
- Rücknahmen (Abholung, Zahlung, Teilnahme) nur über `apps/ausgabe/korrekturen.py`
  (`zuruecknehmen()`, Korrekturwünsche, ADR 0035).
- App `statistik` (ADR 0036): Abfragen in `auswertung.py`, Verbandsstatistik in `verband.py`
  (ADR 0081, Stichmonat mit Vorjahresvergleich), SVG-Diagramme in `diagramme.py`
  (feste Farbreihenfolge `reihe-0…7` in bintafeln.css, Texte immer `escape()`), jeder Abschnitt
  auch als Tabelle und CSV.
- Löschen in der Oberfläche nur über `apps.core.papierkorb.loeschen(...)` (Papierkorb, ADR 0073;
  `recht=` wer wiederherstellen darf, `kundennummer=` bei Kundendaten), nie direkt `delete()`;
  verschlüsselte Datei im Modell als `PRIVATDATEI = (ordner, feld)`. Löschfristen löschen direkt.
- Datensicherung in der Oberfläche: `apps/core/datensicherung.py` (Export mit Passwort,
  `lesen()`, `vorschau()`, `zuruecklesen(ersetzen=False)` löscht nie; ADR 0037). Neue Modelle
  landen automatisch im passenden Bereich (`modelle()`); vorübergehende Daten in `AUSGENOMMEN`.
  Signale auf `post_save` müssen `raw` beachten.
- Handbuch im Programm (ADR 0038): Kapitel in `apps/core/hilfe.py` (mit Rechten) und
  `templates/hilfe/<kennung>.html`. **Neue oder geänderte Funktionen aktualisieren das passende
  Kapitel im selben PR** (wie README); `tests/test_hilfe.py` prüft Vollständigkeit.
- Einstellungsseiten speichern sofort: Formular mit `data-autosave` (`static/js/autosave.js`,
  ADR 0076); die Ansicht leitet nach Erfolg weiter und zeigt Fehler wie gewohnt am Feld.
- Menü links: Einträge je Rolle in `apps/core/menue.py` (neue Seiten dort eintragen statt
  Links in die Seiten zu setzen). Alles Einstellungsartige unter „Einstellungen“, jede Adresse
  nur einmal (`tests/test_menue.py`); Fahrdienst und Dienstplan unter „Dienstpläne“.
  Werkseinstellungen eines Kontos: `verwaltung.werkseinstellungen()`; `Benutzer.ansicht_stand`
  lässt den Browser gemerkte Ansichten (localStorage `bintafeln-*`) vergessen.
- Mitarbeitende: Logik und Schutzregeln in `apps/konten/verwaltung.py` (nie löschen, nur
  sperren; ADR 0015). `Benutzer.passwort_aendern` erzwingt über
  `PasswortAendernMiddleware` ein neues Passwort, bevor die Zwei-Faktor-Einrichtung kommt.
  Stammdaten, Wiedervorlagen, Führerschein-Kopie und Löschfrist in `apps/konten/personal.py`
  (ADR 0017); Fotos verkleinert `privatdateien.speichern()` nach `FotoEinstellungen` (ADR 0064).
  App `personal` (Rolle Personal): Verträge, Abwesenheiten, Stunden; Rechenregeln
  in `apps/personal/berechnung.py` (ADR 0018). Arbeitszeiterfassung (Stempeln, vergessenes
  Gehen, Überschneidungen) in `apps/personal/arbeitszeit.py`, Pausenabzug in
  `berechnung.arbeitstag()` (ADR 0020). Verschlüsselte Dateien nur über
  `apps.core.privatdateien`.
- App `antraege` (Modul 3, ADR 0024): öffentliches Formular `/antrag/<sprache>/` in
  `views_oeffentlich.py`, Bearbeitung in `views.py`, Fristen `models.fristen_anwenden()`.
  Antragsnummer `Antrag.laufnummer` (fortlaufend, Startwert in `AntragEinstellungen`).
  Aufnahme-Assistent: Logik in `aufnahme.py` (Dubletten, Gültigkeit, freie Gruppen,
  `uebernehmen()`), Schritte in `views_aufnahme.py` (ADR 0028). Import-Abgleich:
  `importieren.abgleich()`, `uebernehmen(..., behalten=…)`.
  Eigene Texte der Tafel (`AntragText`) dürfen HTML enthalten und laufen immer durch
  `apps.core.html.anzeigen()`/`bereinigen()` (nh3), nie ungefiltert mit `|safe`.
  Farbe der Tafel als CSS-Variablen über `templates/includes/farben.html`
  (`apps/core/farben.py`); in CSS nur `var(--akzent)` usw., keine festen Akzentfarben.
  Einzugsgebiet (PLZ/Orte, markieren oder sperren) in `apps/antraege/gebiet.py` (ADR 0083).
  KI-Übersetzung der eigenen Texte nur über `apps/antraege/uebersetzen.py` (ADR 0082; in Tests
  `uebersetzen._client` ersetzen).
  Texte je Sprache in `apps/antraege/uebersetzungen/<code>.json` (Grundlage `de.json`); neue
  Texte in **allen** Sprachdateien ergänzen, `tests/test_antraege.py` prüft Vollständigkeit
  und Platzhalter.
- PDFs nur über `apps.core.pdf` (`Pdf`-Rahmen, `pdf_antwort()` ohne Zwischenspeichern; ADR 0021).
  Auskunft Art. 15: `apps/kunden/auskunft.py` und `apps/konten/auskunft.py`, Kundenausweis
  `apps/kunden/ausweis.py` nach `AusweisVorlage` (ADR 0027; Kundennummer und Barcode Pflicht),
  Kassenbericht `kasse.bericht_pdf()`. Neue gespeicherte Daten zu Personen gehören auch in die
  Auskunft. In Tests liest die Fixture `pdf_text` den Text aus
  dem PDF.
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
  Versionen `JJJJ.M.N` vergibt `.github/workflows/version.yml` nach jedem Merge, `update` bietet
  sie zur Auswahl an (auch ältere; dann Migrationen rückwärts, deshalb jede Migration
  umkehrbar halten), `bintafeln/version.py` liest die Datei VERSION (ADR 0023). Mehrere
  Installationen hinter `docker/gemeinsamer-proxy` über `docker/hinter-proxy.yml`, hinter einem
  fremden Proxy (z. B. Synology) über `docker/hinter-fremdem-proxy.yml` (ADR 0069); Demo-Betrieb
  mit `BINTAFELN_DEMO` und `apps/core/demo.py` (ADR 0022). Was Demo-Besucher nutzen
  könnten, um andere auszusperren, mit `nicht_in_demo` sperren.
  Sicherungsskript im Dienst `backup`: `docker/backup/sicherung.sh`; es liest die
  Sicherungsaufträge (`SicherungsAuftrag`, ADR 0042) per psql aus der Datenbank und meldet den
  Stand zurück. Update aus der Oberfläche: `apps/core/update.py` tauscht nur Dateien mit dem
  Dienst `updater` (`docker/updater/updater.sh`) aus; bintafeln selbst bekommt nie Zugriff auf
  Docker (ADR 0043). Warnung bei wichtigen Updates (ADR 0084): `update.warnung()`, Stufe aus
  dem PR-Label (`sicherheit`, `wichtig`, `neue-funktion`) als `stufe=…` im Tag, später bekannte
  Lücken in `docs/sicherheitshinweise.txt`. **Beim Anlegen eines PR die passende Stufe als Label
  vorschlagen.**
- Zuschaltbare Module (ADR 0049): eigene App mit `modul.py` (`apps.core.module.Modul`: Rechte,
  Vorgaben, Menü, Hilfe-Kapitel mit Vorlage in der App, Pfade, Bereich der Datensicherung),
  eingetragen in `settings.BINTAFELN_MODULE`; jede Tafel schaltet sie in den Tafel-Einstellungen
  ein. Kein modulspezifischer Code im Kern; ausgeschaltete Module sperrt die `ModulMiddleware`.
  Erstes Modul: `aufruf` (ADR 0050, Regeln in `apps/aufruf/ablauf.py`, Seiten aus dem
  bisherigen Aufrufsystem in `apps/aufruf/templates/aufruf/`, Geräte ohne Anmeldung nur über
  den Schlüssel im Link). `warteliste` (ADR 0051, Regeln in `apps/warteliste/ablauf.py`,
  `Wartestand` je Antrag). `wetter` (ADR 0053, Abruf bei Open-Meteo nur im Server in
  `apps/wetter/wetter.py`, in Tests `wetter._json` ersetzen). `wochenuebersicht` (ADR 0054,
  Rechnung in `apps/wochenuebersicht/auswertung.py`, PDF hoch/quer in `pdf.py`). `abrechnung`
  (ADR 0060, Regeln in `apps/abrechnung/ablauf.py`, Einnahmen aus der Kasse, beim Einreichen
  festgehalten; Quittungen über `privatdateien`). `listen` (ADR 0063, Katalog in
  `apps/listen/katalog.py`, Spalten mit Recht in `spalten.py`, Rechnen in `abfrage.py`). `links`
  (ADR 0057, Kacheln auf der Startseite, Sichtbarkeit über ein Recht). `fahrdienst` (ADR 0074,
  Regeln in `apps/fahrdienst/plan.py`, Plan aus fester Besetzung, Ausfall und Ersatz je Tag).
  `dienstplan` (ADR 0077, wie Fahrdienst je Ausgabestelle und Ausgabetag, Regeln in
  `apps/dienstplan/plan.py`, `Helfer` mit oder ohne Konto). Telegram für beide: `apps/core/telegram.py`.
  Ausfälle beider: Dauer und „wieder gesund“ (`Ausfall.gesund_ab`, nie automatisch zurück) in
  `apps/core/ausfall.py` (ADR 0085).
  `aushang` (ADR 0080, Aushang-Monitore ohne Anmeldung über den Schlüssel im Link; Seiten bieten
  Module über `Modul.aushang` als `Aushangseite` an, z. B. `apps/dienstplan/aushang.py`; Inhalt in
  `apps/aushang/anzeige.py`, Wechsel, große Ansicht und Dialog in `static/js/aushang.js`; nur Namen
  zeigen; Ändern am Monitor nur mit persönlicher PIN über `apps/aushang/pin.py`, die Rechte prüft
  `Aushangseite.aendern` des Moduls).
  Hooks `Modul.fristen`, `Modul.auskunft_mitarbeiter`, `Modul.aushang`,
  `Modul.einlass`, `Modul.auskunft_antrag`, `Modul.kopfzeile`, `Modul.seitenleiste`, `Modul.suchen`,
  `Modul.startseite`, `Modul.mein_konto`. Programmname nur in
  `bintafeln/programm.py`; die Kopfzeile kürzt `static/js/kopfzeile.js` über `.kuerz-1…5`.
  Übersicht der übernommenen Altprogramme: `docs/altprogramme.md`.
- Datenimport aus CSV/Excel (ADR 0078): App `datenimport` – `lesen.py` (CSV/xlsx), `zuordnung.py`
  (Spaltenvorschlag, Vorlagen), `abgleich.py` (neu/Konflikt/Ergänzung/Dublette/fehlt, Wahl je
  Feld, für alle Ziele gleich), Ziele in `ziele.py` (Ausgabestellen, Kundengruppen, Mitarbeitende, Adressbuch,
  Mitglieder, Kundenstamm; Kontobuchungen über `buchungen.csv`, `Buchung.importiert`).
  Neue Ziele dort ergänzen. Kundenstamm: Assistent schreibt ins Importformat um, Ergänzen in
  `apps/kunden/import_ergaenzen.py`; Haushalt in den Papierkorb über `apps/kunden/entfernen.py`.
- Überraschungen auf der Anmeldeseite an Festtagen: `apps/core/anlaesse.py` und
  `templates/includes/anlass.html` (SVG + CSS, kein JavaScript; ADR 0079).
- Spenden: Import in `apps/spenden/importieren.py` (ADR 0055, `belegnummer` gegen Dubletten),
  Dankesbriefe und hochgeladene Belege in `apps/spenden/dank.py` (ADR 0056; PDFs zusammenfügen
  mit `pypdf`, Mail-Anhänge über `mail.senden(..., anhaenge=…)`).
- Browser-Tests in `tests/e2e/` (Playwright, ADR 0066): nur mit `pytest -m e2e`, Abhängigkeiten in
  `requirements-e2e.txt`, eigener CI-Job `e2e`. JavaScript-Fehler lassen sie scheitern; neue
  JavaScript-Funktionen dort mit einem Ablauf abdecken.
- Commit-Beschreibungen: Stichpunkte mit „- “ erscheinen auf der Update-Seite unter „Was ist neu?“
  (`aenderungen()` in `docker/updater/updater.sh`), also verständlich für die Tafeln formulieren.
- Shell-Skripte müssen `shellcheck` bestehen. Änderungen an Sicherung oder Wiederherstellung
  deckt `tests/sicherung_e2e.sh` ab (läuft in CI im Job `docker`).
