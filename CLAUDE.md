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
- **Repository:** öffentlich. Alles im Repository muss veröffentlichungsfähig sein.
- **Technik:** Python, Django (aktuelle LTS), PostgreSQL, Auslieferung per Docker Compose
  (`app`, `db`, `proxy` mit Caddy, `backup` für die verschlüsselte Sicherung, siehe ADR 0008,
  `updater` für das Update aus der Oberfläche, ADR 0043, auf Wunsch `abruf`, ADR 0127).
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
  `views_dokumente.py`; am Einlass legt `views_dokumente.foto` Fotos von Nachweisen ab (Recht
  `kunden.dokument_foto`, nur ablegen, ADR 0122).
  Historie (`HaushaltEreignis`, ADR 0031) über `apps/kunden/historie.py`: Schnappschuss vor und
  nach jeder Änderung am Kundenstamm (`festhalten()`, beim Import `import_festhalten()`).
  Ohne gültigen Ausweis keine Kundengruppe (ADR 0061): `apps/kunden/gruppen.py` (`pruefen()` nach
  jeder Änderung, `regel_anwenden()` täglich und beim Import), Zeiten in `Gruppenzeit`.
  `ausgabe` (Einlass; Beitrag über `AusgabeEinstellungen.beitrag_fuer()` – zahlende Personen
  ab Alter × Betrag, Zusatzbeiträge optional, `BeitragsfreierZeitraum` (für alle oder einzelne
  Ausgabestellen; welche zählt: `models.stelle_von()`);
  Ampel-Regeln als reine Funktion in `apps/ausgabe/ampel.py`,
  Einstellungen in `AusgabeEinstellungen`; Kundenkonto nur über `apps/ausgabe/konto.py`
  buchen, nie `Haushalt.kontostand` direkt ändern, ADR 0014; einzelne Buchungen ändern/löschen nur über
  `konto.aendern()`/`korrekturen.zuruecknehmen()` (Recht `konto.buchung_aendern`); Zahlung ohne Abholung mit Minus = Auszahlung; importierte Tageslisten (auch „Besuche & Konto nachtragen“) bucht
  `konto.zahlungen_aus_kontostand()` (gezahlt = Kosten nach Beitragsregel + Kontostand danach − vorher,
  alte Abgleich-Korrekturen über `konto.abgleiche_nachrechnen()`; alte Abholungen ganz ohne Kassendaten nur als gekennzeichnete
  Schätzung über `konto.alte_abholungen_schaetzen()`, rücknehmbar mit `schaetzung_entfernen()`), `beitrag` ist nie Bargeld; Kasse-Auswertung in
  `apps/ausgabe/kasse.py`; Kamera-Scanner `static/js/kamera_scanner.js` für Felder mit
  `data-kamera`, Bibliothek fest unter `static/vendor/barcode-detector`, kein CDN, ADR 0029;
  Schließzeiten je Ausgabestelle (`Schliesszeit`, ADR 0144): zählen im Vorauszahlungs-Vorschlag nicht mit
  (`konto.vorschlaege()`), Hinweis am Einlass über `stelle.kontext`;
  Sonderaktionen: Regeln in `apps/ausgabe/sonderaktionen.py`, `Teilnahme` an der Kundennummer,
  ADR 0032; aktuelle Ausgabestelle nur über `apps/ausgabe/stelle.py` (`aktuelle()`, Auswahl oben
  im Menü, `Benutzer.gewaehlte_stelle`, Fortschritt in der Kopfzeile, ADR 0067); wer an einem
  Tag dran ist (auch Sonderausgaben) nur über `apps/ausgabe/ausgabetag.py` (ADR 0072).
  Merkmale (Ja/Nein-Zusatzfelder am Einlass und auf dem Ausweis) in `apps/kunden/merkmale.py`,
  mitgelieferte in `FESTE_MERKMALE` (ADR 0071).
  Sammel-Verlängerung der Ausweise: Regeln in `apps/kunden/verlaengerung.py`, Bedingungen in
  `KundenEinstellungen.verlaengern_*`, Anliegen der `Nachricht` in `apps/core/auswahl.py` (ADR 0068).
  Krankmeldung eines Kunden: `Notiz` mit `krank_von/bis/grund`, Logik in `apps/kunden/krankmeldung.py`,
  zuschaltbar, auch rückwirkend; bleibt nach dem Ende stehen und wird erst gelöscht, wenn der Kunde
  wieder abgeholt hat – nie wegen des Endes (ADR 0075).
  `Abholung.save()` setzt eine fehlende Ausgabestelle aus der Kundengruppe des Haushalts
  (`stelle_der_gruppe()`); `bulk_create` umgeht das, dort selbst setzen (wie `importieren._abholung`).
  Liste aller Notizen (Filter, Export, Löschen in den Papierkorb; Recht `kunden.notizen_loeschen`) in
  `apps/kunden/views_notizen.py`, aller Anmerkungen in `views_anmerkungen.py` (ADR 0143; dort auch „Angehakte in Notizen
  umwandeln“, `umwandeln()` – verschiebt, deshalb ohne Papierkorb); „Angehakte
  löschen“ über `static/js/liste_loeschen.js`.
  Geplantes neues Maximum einer Kundengruppe (ADR 0174): `maximum_neu`/`maximum_ab`, am Tag
  übernimmt `verlegung.maxima_anwenden()`; sonst überall `maximum`, nur wer vorausschaut (Vorschau
  der Wochenübersicht) nimmt `maximum_am(datum)`.
  Wechselwunsch eines Kunden („Will wechseln“ bei den Notizen, ADR 0173): `Wechselwunsch` an der
  Kundennummer, Regeln nur in `apps/kunden/wechsel.py` (`moeglichkeiten()`, `eintragen()` – prüft
  die Erreichbarkeit, `genehmigen()`/`ablehnen()` mit Mail an den Kunden), Ansichten in
  `views_wechsel.py`; entscheiden nur mit dem Recht `kunden.wechsel_entscheiden`.
  Platz per E-Mail anbieten (ADR 0175): `wechsel.anbieten()` – Link mit Zufallsschlüssel (nur die
  Prüfsumme wird gespeichert), öffentliche Seite `kunden:wechsel_angebot` zeigt nur das Angebot,
  bestätigt wird erst per Knopf; „Ja“ = `angebot_beantworten()` → `genehmigen()`; laufende
  Angebote reservieren den Platz (`gruppen.reservierte_zugaenge()`). Immer Deutsch, darunter die
  Sprache des Kunden: Texte in `apps/kunden/wechsel_texte/<code>.json` – neue Texte in allen Dateien.
  Vor dem Senden immer die Vorschau (`angebot_vorschau()`); nur freie Plätze (`angebot_pruefen()`).
  Von der Tafel aus (Kundenseite, Art `tafel`): `von_uns_anbieten()`, volle Gruppe nur `vormerken()`.
  Auf der Kundenseite unter „Angaben“: `wechsel.angebot_am_kunden()` (läuft / bis 14 Tage nach
  Antwort oder Ablauf); Zusage auf anderem Weg trägt die Verwaltung über
  `angebot_zusage_eintragen()` ein (Recht `kunden.wechsel_entscheiden`).
  Status nach Sperre und Ausweis (ADR 0176): `apps/kunden/status.py` – laufende `Sperre` → „gesperrt“
  (geht vor), Ausweis abgelaufen → „pausiert“, sonst „aktiv“; nur für Aktive und vom Programm
  Umgestellte (`Haushalt.status_automatisch`), Schalter
  `KundenEinstellungen.status_nach_ausweis` (Vorgabe aus); `Haushalt.save()` führt `status_seit`.
  Status „verstorben“: zählt wie „beendet“ nicht mit (`Haushalt.NICHT_MEHR` statt nur BEENDET
  ausschließen), nach `verstorben_loeschen_monate` in den Papierkorb.
  Kunden herausnehmen (ADR 0177): `apps/kunden/herausnehmen.py` – Knopf auf der Kundenseite nur mit
  `kunden.herausnehmen` und wenn `faellig()` (wie die Liste „Lange nicht gekommen“,
  `KundenEinstellungen.herausnehmen_nach_tagen`); Ausweis bis gestern + `Sperre(herausnahme=True,
  ausweis_vorher=…)`, `zuruecknehmen()` stellt das Datum wieder her.
  Einkommensart vieler Haushalte auf einmal ändern (nach Alter der Hauptperson, erst ansehen, dann
  ändern, in Portionen) in `apps/kunden/views_einkommensart.py` (ADR 0146).
  Notizen an die Ausgabestelle (`Notiz.an_stelle`, Startseite, Antwort beim Ausweisdruck) in
  `apps/kunden/an_stelle.py`; die Antwort „Neuer Ausweis ist gedruckt“ bekommt `Notiz.loeschen_am`
  (`KundenEinstellungen.ausweis_notiz_tage`, Vorgabe 14) und geht dann still in den Papierkorb; feste Notiz-Vorlagen zu `FESTE_ANLIEGEN` (ADR 0070).
  Jeder Druck gemeldeter Ausweise lässt sich als Ganzes zurücknehmen (`Ausweisdruck`,
  `an_stelle.letzte_drucke()`/`druck_zuruecknehmen()`, Abschnitt „Zuletzt gedruckte Ausweise“ auf der
  Nachrichtenseite – ohne Nachfrage; ADR 0167, 0180). Schwerbehinderte (Ausweis mit Rollstuhl-Symbol,
  `merkmale.mit_rollstuhl_ausweis()`) getrennt: `?gemeldet=1&sb=ohne|nur`, der Rest bleibt offen.
  Nachricht einer Ausgabestelle an die Verwaltung ohne Kunden (`StellenNachricht`, Startseite,
  Mail über die Benachrichtigung `nachricht_verwaltung`, Antwort auf der Startseite der Stelle) in
  `apps/kunden/an_verwaltung.py` (ADR 0140).
  Post der Verwaltung an Ausgabestellen (`Rundschreiben`/`PostEmpfang`, Eule in der Kopfzeile über
  `templates/kunden/_eulenpost.html` und `static/js/eulenpost.js`) in `apps/kunden/eulenpost.py` (ADR 0142).
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
- Anschrift in Google Maps (Kundenseite: „Karte“, „Entfernung von der Tafel“): nur Links über
  `apps/core/karten.py` (`zeigen()`, `route()` ab der Anschrift aus den Tafel-Einstellungen), kein
  API-Schlüssel, nichts eingebettet; nur mit `kunden.kontakt`.
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
  verschlüsselte Datei im Modell als `PRIVATDATEI = (ordner, feld)`. Löschfristen löschen direkt;
  Ausnahme Notizen: auch automatisch über `kunden.models.notizen_in_papierkorb()`, `still=True`
  (zählt nicht als neu im Menü).
- Datensicherung in der Oberfläche: `apps/core/datensicherung.py` (Export mit Passwort,
  `lesen()`, `vorschau()`, `zuruecklesen(ersetzen=False)` löscht nie; ADR 0037). Neue Modelle
  landen automatisch im passenden Bereich (`modelle()`); vorübergehende Daten in `AUSGENOMMEN`.
  Signale auf `post_save` müssen `raw` beachten.
- Handbuch im Programm (ADR 0038): Kapitel in `apps/core/hilfe.py` (mit Rechten) und
  `templates/hilfe/<kennung>.html`. **Neue oder geänderte Funktionen aktualisieren das passende
  Kapitel im selben PR** (wie README); `tests/test_hilfe.py` prüft Vollständigkeit.
  Bilder im Handbuch: `{% load handbuch %}{% hilfe_bild "name" "① … ② …" %}`, erzeugt nur
  mit erfundenen Daten in `tests/e2e/test_hilfe_bilder*.py` (Werkzeug `hilfe_bilder.py`,
  Pfeile/Rahmen über `Marke`, Fixture `muster`; neue Seiten mit Oberfläche bekommen ein Bild);
  ändert sich eine abgebildete Seite, Bilder mit `BINTAFELN_HILFE_BILDER=1` neu erzeugen.
- Suchfelder in Listen suchen beim Tippen: Feld mit `{% live_suche %}` (ab 2 Zeichen, htmx),
  Treffer der Seite in `<div id="ergebnis">`; nur dieser Bereich wird ausgetauscht.
  Jedes Filterformular bekommt `{% filter_zuruecksetzen %}` (Knopf „Zurücksetzen“; Angaben, die
  bleiben sollen, als Argumente, z. B. `"sort"`).
  Listen, aus denen man Einträge öffnet, merken Filter, Suche und Sortierung am Konto:
  `listen.filter_merken(request, liste, parameter)` am Anfang der Ansicht (Rückgabe ausliefern,
  wenn nicht `None`); Jahres- und Datumsfilter nicht merken.
- Listen am Handy: unter 40rem zeigt jede `table.tabelle` ihre Zeilen als Karten mit der
  Spaltenüberschrift vor jedem Wert (`data-titel`); fehlt sie, trägt `static/js/tabellen_titel.js` sie
  aus dem Tabellenkopf nach. Jede Liste braucht deshalb einen `<thead>`.
- Spaltenbreite in Listen per Ziehen: `static/js/spaltenbreite.js` (alle Tabellen in
  `.tabelle-rahmen`, Breiten je Liste im localStorage `bintafeln-breite-…`, Knopf zum Zurücksetzen).
- Lange Mehrfachauswahlen als aufklappbares Menü: Widget `Mehrfachauswahl` (`apps/core/forms.py`,
  `static/js/mehrfachauswahl.js`, Suchfeld ab 8 Einträgen); Felder nur bei passender Auswahl
  zeigen mit `data-zeigen-bei="feld=wert1 wert2"` (`static/js/zeigen_bei.js`).
- Datumsfelder immer TT.MM.JJJJ: im Formular `DatumEingabe` (`apps/konten/forms.py`); ein
  einfaches `<input type="date">` stellt `static/js/datum.js` selbst um (Textfeld TT.MM.JJJJ, das
  versteckte Feld mit dem Namen schickt weiter JJJJ-MM-TT). Öffentliche Seiten binden `datum.js` ein.
- Nach dem Absenden eines Formulars an dieselbe Seite bleibt die Position (`static/js/position.js`);
  Knöpfe, deren Ergebnis weiter unten erscheint (Vorschau, Prüfen), bekommen `data-ziel="<id>"`.
  PDFs in einem neuen Fenster öffnen per Link oder GET-Formular mit `target="_blank"`
  (`static/js/neues_fenster.js` öffnet es per `window.open`); in der iPad-App vom Home-Bildschirm
  käme man aus einem per POST geöffneten PDF nicht zurück. POST-Formulare mit `formtarget="_blank"`
  bekommen deshalb `@im_fenster` aus `apps.core.pdf` (äußerster Decorator): in der App geht das
  Formular im Hintergrund ab, die Eingaben kommen für einen Aufruf in die Sitzung, ein Dialog
  bietet „PDF öffnen“ als Link an.
- Einstellungsseiten speichern sofort: Formular mit `data-autosave` (`static/js/autosave.js`,
  ADR 0076); die Ansicht leitet nach Erfolg weiter und zeigt Fehler wie gewohnt am Feld.
  Ebenso Seiten, die einen vorhandenen Datensatz bearbeiten (ADR 0145): `data-autosave` nur mit
  `pk`, beim Neuanlegen bleibt der Knopf und heißt „Anlegen“; Felder, die halb getippt Schaden
  anrichten (Kundennummer), bekommen `data-autosave-spaet`; ändert das Speichern die Adresse der
  Seite, `data-autosave-folgen`. Knöpfe mit eigener Aktion und Löschen bleiben Knöpfe;
  stehen sie im selben Formular (Vorschau), bekommt der Speichern-Knopf `data-autosave-knopf`.
  Zeilentabellen (Formsets) auf solchen Seiten: `<tbody id="…" data-autosave-zeilen>`, sonst legt
  das nächste Speichern neue Zeilen doppelt an.
- Menü links: Einträge je Rolle in `apps/core/menue.py` (neue Seiten dort eintragen statt
  Links in die Seiten zu setzen). Alles Einstellungsartige unter „Einstellungen“, jede Adresse
  nur einmal (`tests/test_menue.py`); auch das laufende Verwalten der Ausgabe (Sonderaktionen,
  Korrekturwünsche, Post an Ausgabestellen) steht unter „Einstellungen → Ausgabe“, nicht unter „Ausgabestelle“; Fahrdienst und Dienstplan unter „Dienstpläne“.
  Ein Modul kann einen eigenen Hauptbereich mitbringen (er steht nach den Dienstplänen): „Touren“
  mit allem zur Tourenplanung, auch „Einrichten“ (Warengruppen, Fahrzeuge, Zentrale – Recht
  `touren.planen`, `views_lieferscheine.einrichten`); unter „Einstellungen → Touren“ steht nur, was
  der Admin entscheidet (Mailversand, Kartenschlüssel, ECO, Aufbewahrung).
  Werkseinstellungen eines Kontos: `verwaltung.werkseinstellungen()`; `Benutzer.ansicht_stand`
  lässt den Browser gemerkte Ansichten (localStorage `bintafeln-*`) vergessen.
- Adressnummern (ADR 0133): `Adresse.nummer` vergibt `Adresse.save()` über
  `adressen.models.naechste_adressnummer()` (Zähler `AdressEinstellungen`, Vorgabe 2000, überspringt
  gleich lautende Mitgliedsnummern); wer als Mitglied angelegt wird, setzt vorher
  `adresse.als_mitglied = True`. Angezeigt wird `Adresse.nummer_anzeige` (Mitgliedsnummer vor
  Adressnummer).
- Mitarbeitende: Logik und Schutzregeln in `apps/konten/verwaltung.py` (nie löschen, nur
  sperren; ADR 0015). Liste in `apps/konten/views_mitarbeitende.py` (getrennte Namen, wählbare
  Spalten über `apps/core/listen.py`, Export über `apps/core/listenexport.py`, Suche). Das PDF
  einer Liste lässt ausgeblendete Spalten weg (`ausliefern(ohne_spalten=listen.pdf_ohne(…))`,
  ADR 0096), die CSV behält alle – neue Listen mit Spaltenauswahl ebenso anschließen.
  Leerspalten im PDF (eine oder zwei, zum Eintragen/Unterschreiben): zentral über
  `listenexport.leerspalten()`/`mit_leerspalten()`, Felder im Baustein `includes/leerspalten.html`.
  Listen, deren Zeilen an einer Adresse hängen (Mitglieder, Spenden), bieten deren Felder als
  Spalten an: `listen.ADRESS_SPALTEN`/`adress_spalten()` (nur mit `adressen.sehen`), Bausteine
  `includes/adress_spalten_kopf.html`/`…_zellen.html`; in der Vorgabe ausgeblendet über
  `listen.standard_aus()`.
  Reihenfolge der Spalten je Person (Team, Adressbuch, Mitglieder, Spenden): Pfeile unter
  „Spalten wählen“ (`static/js/spalten_folge.js`, Speichern über `listen.spalten_aus_post()`);
  Vorlagen kennzeichnen jede Zelle mit `{% spalte "schluessel" %}` und umschließen die Tabelle mit
  `{% spaltenfolge folge %}` (`listen.spalten_ordnen()`), `SPALTEN` steht in der Reihenfolge der
  Vorlage; das PDF folgt über `ausliefern(reihenfolge=listen.pdf_folge(…))`.
  Personalnummer (ADR 0116, ersetzt ADR 0101): `Stammdaten.personalnummer`, eigener Nummernkreis –
  unabhängig von den Mitgliedsnummern, dieselbe Zahl darf in beiden vorkommen. Automatisch aus
  `PersonalEinstellungen.naechste_personalnummer` über `verwaltung.naechste_personalnummer()` in
  `verwaltung.personalnummer_zuweisen()` (für jeden Mitarbeitenden, auch Mitglieder); von Hand
  gesetzte Nummern über `verwaltung.personalnummer_verbraucht()`. Anzeige in der
  Mitarbeitendenliste über `verwaltung.personennummer()` (immer die Personalnummer).
  `Benutzer.passwort_aendern` erzwingt über
  `PasswortAendernMiddleware` ein neues Passwort, bevor die Zwei-Faktor-Einrichtung kommt.
  Glückwunsch-Mail zum Geburtstag (ADR 0178): `apps/konten/geburtstagsmail.py` – Text aus der
  Serienbrief-Vorlage mit `Vorlage.verwendung` (Geburtstag / nachträglich), immer erst die Seite mit
  der fertigen, änderbaren Mail, nie ungesehen senden; `GeburtstagMail` merkt 30 Tage, wer schrieb. Vormerken (ADR 0179):
  `GeburtstagVormerkung` mit festem Text und Uhrzeit je Mail, `faellige_senden()` läuft im Befehl
  `benachrichtigungen_senden`, Meldung an die vormerkende Person über die Benachrichtigung
  `geburtstagsmail`.
  Geburtstagsbrief auf der Startseite (ADR 0170): `apps/konten/geburtstage.py` (`brief()`,
  `gesehen()`, `fristen_anwenden()`), eigener Glückwunsch für jede Person, zu allen mit dem Recht
  `mitarbeitende.geburtstagsbrief`; gemerkt je Konto in `GeburtstagGruss` (vorübergehend), Vorlage
  `konten/_geburtstagsbrief.html`, `static/js/geburtstagsbrief.js`, Schalter
  `TafelEinstellungen.geburtstagsbrief`.
  Stammdaten, Wiedervorlagen, Führerschein-Kopie und Löschfrist in `apps/konten/personal.py`
  (ADR 0017); Fotos verkleinert `privatdateien.speichern()` nach `FotoEinstellungen` (ADR 0064).
  App `personal` (Rolle Personal): Verträge, Abwesenheiten, Stunden; Rechenregeln
  in `apps/personal/berechnung.py` (ADR 0018). Wer Arbeitszeit erfasst, entscheidet nur
  `arbeitszeit.erfasst()` (`Benutzer.zeiterfassung` je Person vor `ArbeitszeitEinstellungen.aktiv`);
  ohne Erfassung kein Stundenkonto. Arbeitszeiterfassung (Stempeln, vergessenes
  Gehen, Überschneidungen) in `apps/personal/arbeitszeit.py`, Pausenabzug in
  `berechnung.arbeitstag()` (ADR 0020). Verschlüsselte Dateien nur über
  `apps.core.privatdateien`.
- App `antraege` (Modul 3, ADR 0024): öffentliches Formular `/antrag/<sprache>/` in
  `views_oeffentlich.py`, Bearbeitung in `views.py`, Fristen `models.fristen_anwenden()`.
  Antragsnummer `Antrag.laufnummer` (fortlaufend, Startwert in `AntragEinstellungen`).
  Aufnahme-Assistent: Logik in `aufnahme.py` (Dubletten, Gültigkeit, freie Gruppen,
  `uebernehmen()`), Schritte in `views_aufnahme.py` (ADR 0028). Import-Abgleich:
  `importieren.abgleich()`, `uebernehmen(..., behalten=…)`.
  Ähnliche Kunden sucht `aufnahme.kandidaten()`/`treffer()` über den Trigramm-Index
  `Person.such_name` (pg_trgm, ADR 0102), damit der Abgleich bei großem Kundenstamm nicht jeden mit
  jedem vergleicht; Namensnormalisierung in `apps/kunden/namen.py` (auch von `aufnahme.normal`
  genutzt). `such_name` wird abgeleitet (in `Person.save()` und im Import `_person()`), nie von Hand.
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
- Text aus anderen Programmen (Importe, ausgelesene PDFs) enthält Ligaturen und unsichtbare
  Zeichen, die im Druck als schwarzer Block erscheinen: `apps.core.zeichen.bereinigen()` beim
  Hereinkommen (`Adresse.save()`, PDF-Text) und als Netz beim Drucken (`pdf.text()`).
- PDFs nur über `apps.core.pdf` (`Pdf`-Rahmen, `pdf_antwort()` ohne Zwischenspeichern; ADR 0021).
  Druckansicht für Tablets im Kiosk-Modus (ADR 0141): `apps.core.druckansicht.DruckansichtMiddleware`
  zeigt PDFs als Seite mit Drucken/Mail/Zurück (Vorgabe für Ausgabestellen-Konten, sonst je Gerät
  per Cookie unter „Mein Konto“; `?_pdf=roh` liefert das PDF selbst). Mail nur an die angebotenen Adressen;
  persönliche Konten auch an eine freie (`druckansicht.frei_erlaubt()`), Stellen-Konten nie. In der App vom Home-Bildschirm
  und auf diesen Geräten öffnet `static/js/pdf_fenster.js` PDFs nie in einem neuen Fenster, sondern
  über der Seite; „Drucken“ teilt das PDF über das Teilen-Menü des Geräts (Web Share).
  Auskunft Art. 15: `apps/kunden/auskunft.py` und `apps/konten/auskunft.py`, Kundenausweis
  `apps/kunden/ausweis.py` nach `AusweisVorlage` (ADR 0027; Kundennummer und Barcode Pflicht),
  Kassenbericht `kasse.bericht_pdf()`. Neue gespeicherte Daten zu Personen gehören auch in die
  Auskunft. In Tests liest die Fixture `pdf_text` den Text aus
  dem PDF.
- Mails nur über `apps.core.mail.senden()` (Mailserver aus der Datenbank, verständliche
  `MailFehler`; mit `art=` aus `mail.ARTEN`, bei Zugangsdaten `vertraulich=True` – jede Mail
  landet im Archiv `GesendeteMail`, Frist `MailEinstellungen.archiv_tage`, ADR 0124). Benachrichtigungen an Mitarbeitende nur über
  `apps.core.benachrichtigung.melden(art, an, …, schluessel)` (Häufigkeit je Person, Erledigtes
  entfällt über `Art.offen`; neue Arten in `KERN` bzw. `Modul.benachrichtigungen`; ADR 0086). Jede Mail
  steht auf der Seite „Mail-Empfänger“ (ADR 0125): neue `Art` mit `wann` und `an` oder – bei Mails
  an eine Gruppe – `wahl=Empfaengerwahl(...)` (Empfänger dann über `benachrichtigung.empfaenger()`, bei Vorgabe
  im Einzelfall `fest=False` und `benachrichtigung.an(kennung, vorgabe)`; ohne Häkchen bekommt niemand die Mail,
  nie eigene Auswahlfelder); andere Mails als `Mail` in `apps/core/mailuebersicht.py` bzw. `Modul.mails`. Geheimnisse in der Datenbank nur über `apps.core.geheimnis` verschlüsselt
  speichern (ADR 0016). In Tests landen Mails in `django.core.mail.outbox`.
- Push-Nachrichten aufs Handy nur über `apps/core/push.py` (Web Push mit `cryptography`, ein
  Schlüssel der Tafel in `PushEinstellungen`, ADR 0134, 0158): an Mitarbeitende mit
  `push.an_benutzer(konten, titel, text, link, kennung)`, nach dem Speichern über
  `push.nach_speichern(...)`; eingeschaltet wird je Gerät nur auf „Mein Konto“ (`PushAbo`,
  `static/js/push.js`, Service Worker `/push-sw.js`). In Tests `push._senden` und
  `push._im_hintergrund` ersetzen.
- Gemeinsamer Cache in der Datenbank (ADR 0093): `CACHES` = DatabaseCache, Tabelle `bintafeln_cache`
  (Migration `core/0022`); nötig, weil mehrere gunicorn-Prozesse laufen und ein prozesslokaler
  Cache Zähler nicht teilt und beim Update vergisst. Darauf bauen die Anmelde-Sperre
  (`apps/konten/anmeldesperre.py`, Fehlversuche je Benutzername und Dauer aus
  `AnmeldeEinstellungen`, Vorgabe 5 → 15 min; Admin hebt sie sofort auf, ADR 0120) und weitere Drosseln. In Tests
  LocMemCache (`settings_test.py`), der Datenbank-Cache ist mit einem eigenen Test abgedeckt.
- Freier Platz auf der Festplatte des Servers (ADR 0169): `apps/core/speicherplatz.py` (`stand()`,
  `melden()` – einmal je Stufe eine Mail über die Benachrichtigung `speicher_knapp`), Grenzen in
  `SpeicherWarnung`, Balken auf „Speicher und Fotos“, Hinweis auf der Startseite. In Tests
  `speicherplatz._platte` ersetzen.
- Zwei-Faktor: Logik in `apps/konten/zwei_faktor.py`, Durchsetzung in
  `apps.konten.middleware.ZweiFaktorMiddleware`. In Tests Benutzer mit der Fixture `anmelden`
  anmelden (verifizierte Sitzung); ein bloßes `force_login` landet bei Pflicht-Rollen auf der
  Einrichtungsseite.
- Neue Modelle mit Personen- oder Stammdaten bei django-auditlog registrieren
  (`auditlog.register(...)`), Geheimnisse und Passwörter mit `exclude_fields` ausnehmen.
- Betriebsmodus: `BINTAFELN_DOMAIN` leer = Entwicklung (http), gesetzt = Produktion (TLS).
- Freiwillige Meldung im bintafeln-Verzeichnis (ADR 0089): `apps/core/verzeichnis.py` (Name,
  Kontakt, Version, Kennung – nie Personendaten), Empfang beim Herausgeber mit
  `BINTAFELN_VERZEICHNIS_EMPFANG`; in Tests `verzeichnis._senden` ersetzen.
- Betrieb auf dem Server über `./betrieb` (update, sichern, wiederherstellen, schluessel, status).
  Erstinstallation mit einem Befehl: `installieren.sh` (holt das Repository, ruft `./betrieb
  installieren`: Server prüfen – Speicher, Ports, Domain –, Docker, `.env`, starten, warten).
  Versionen `JJJJ.M.N` vergibt `.github/workflows/version.yml` nach jedem Merge, `update` bietet
  sie zur Auswahl an (auch ältere; dann Migrationen rückwärts, deshalb jede Migration
  umkehrbar halten), `bintafeln/version.py` liest die Datei VERSION (ADR 0023). Mehrere
  Installationen hinter `docker/gemeinsamer-proxy` über `docker/hinter-proxy.yml`, hinter einem
  fremden Proxy (z. B. Synology) über `docker/hinter-fremdem-proxy.yml` (ADR 0069); Demo-Betrieb
  mit `BINTAFELN_DEMO` und `apps/core/demo.py` (ADR 0022; erfundene Daten für alle Bereiche in
  `apps/core/demo_daten.py`, fester Startwert – neue Bereiche dort mit Beispielen füllen). Was Demo-Besucher nutzen
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
  den Schlüssel im Link; Wartezeit aufs Handy unter `/warten/` in `apps/aufruf/handy.py`,
  Texte in `apps/aufruf/warten_texte/`, immer Deutsch plus zweite Sprache über `views_warten._zweite()`
  und die Vorlage `aufruf/_zwei.html`, ADR 0090; Push-Nachrichten an Kunden über
  `apps/aufruf/push.py` (wann wer was bekommt; Technik in `apps/core/push.py`), ausgelöst nach
  `ablauf.weiter()`/`starten()`, ADR 0134; aufgerufene Nummern für die Homepage der Tafel über
  `apps/aufruf/homepage.py` – eigener Schlüssel, liest nur, einbettbar nur von
  `AufrufEinstellungen.homepage_adresse`, ADR 0181; den Geräte-Schlüssel nie öffentlich verwenden). `warteliste` (ADR 0051, Regeln in `apps/warteliste/ablauf.py`,
  `Wartestand` je Antrag; Mails deutsch + Sprache aus `sprachen.mail_sprachen()`, Texte je
  Sprache in `apps/warteliste/uebersetzungen/` bzw. `WartelisteText`). `wetter` (ADR 0053, Abruf bei Open-Meteo nur im Server in
  `apps/wetter/wetter.py`, in Tests `wetter._json` ersetzen). `wochenuebersicht` (ADR 0054,
  Rechnung in `apps/wochenuebersicht/auswertung.py`, PDF hoch/quer in `pdf.py`; Vorschau auf
  kommende Wochen über `uebersicht(..., vorschau=Montag)`: geplante Umzüge, `schliesst_am` und
  Schließzeiten je Tag eingerechnet; eigene Listen `EigeneListe`: Querformat mit eigenem Namen und
  eigener Reihenfolge der Tage unter der kurzen Adresse `/liste/<kurz>/`, `auswertung.ordnen()` –
  Namen nie fest im Code). `abrechnung`
  (ADR 0060, Regeln in `apps/abrechnung/ablauf.py`, Einnahmen aus der Kasse, beim Einreichen
  festgehalten; Quittungen über `privatdateien`; eine Abrechnung umfasst 1–6 Monate,
  `Monatsabrechnung.bis`, passende Abrechnung zu einem Monat nur über `ablauf.holen()`/`im_monat()`;
  der Monat heißt in der Oberfläche MMJJ, z. B. 1126 – `ablauf.mmjj()`/`zeitraum_kurz()`, lesen mit
  `monat_aus_text()`, in Adressen bleibt 2026-11; Ausgaben ändern/löschen nur im Entwurf,
  `posten_aendern()`; was auf die Prüfung wartet: `ablauf.eingereichte()`). `listen` (ADR 0063, Katalog in
  `apps/listen/katalog.py`, Spalten mit Recht in `spalten.py`, Rechnen in `abfrage.py`). `links`
  (ADR 0057, Kacheln auf der Startseite, Sichtbarkeit über ein Recht). `fahrdienst` (ADR 0074,
  Regeln in `apps/fahrdienst/plan.py`, Plan aus fester Besetzung, Ausfall und Ersatz je Tag).
  `dienstplan` (ADR 0077, wie Fahrdienst je Ausgabestelle und Ausgabetag, Regeln in
  `apps/dienstplan/plan.py`, `Helfer` mit oder ohne Konto). Telegram für beide: `apps/core/telegram.py`.
  `touren` (ADR 0147, Stationen der Abholtouren als eigene Liste `Station`, nicht das Adressbuch;
  Import nach `docs/importformat-touren.md` in `apps/touren/importieren.py` – Kennung entscheidet;
  Marktliste/Lieferadressen im Exportformat der ECO-Plattform schreibt `listen_einlesen.py` vorher um,
  leere Zellen ändern nichts, nie löschen; einmaliges Übertragen ins Adressbuch in
  `apps/touren/adressbuch.py`; Navigation nur als Link zu Google Maps über `Station.navigation`,
  kein API-Schlüssel, keine Karte. Ausgabestellen der Tafel sind automatisch Stationen (ADR 0171):
  `apps/touren/ausgabestellen.py` (`abgleichen()`, `Station.ausgabestelle`, Kennung `AS-…`); Name,
  Anschrift, Telefon, E-Mail kommen von dort und sind an der Station gesperrt, nie löschen.
  Abholtouren (ADR 0148): `touren.Tour` = Stationsfolge über
  `Halt`, `fahrdienst.Tour` bleibt der Personalplan; Regeln nur in `apps/touren/ablauf.py`
  (`faehrt_am()`, `halte()`, `besetzung()` – aus dem Fahrerplan, sonst `Tour.personen`; dieselbe
  Station darf mehrfach auf einer Tour stehen, `h.durchgang`/`h.besuche`, abgehakt wird je Besuch
  nur über `anfahrten.stand()`, ADR 0172; `routen()`
  höchstens zehn Stationen je Link; `senden()` über die Benachrichtigung `touren_tour`). Ansichten
  für unterwegs in `views_touren.py` zuerst fürs Handy bauen und in Handybreite prüfen.
  Stationen beim Planen suchen: `apps/touren/suche.py` (alle Angaben, ab drei Zeichen, Treffer als
  Baustein `touren/_stationen_treffer.html`); die kurzfristige Tour entsteht in einer Maske
  (`views_touren.tour_neu`, Auswahl über `static/js/stationswahl.js`, neue Adresse über `NeueStationForm`).
  Tourstart (ADR 0150): „Seid ihr …?“ vor einer Tour aus dem Fahrerplan am heutigen Tag, Regeln nur
  in `apps/touren/start.py` (`bestaetigen()` prüft selbst: nur wer auf der Tour eingetragen ist oder
  das Recht `touren.besetzung` hat; Änderung als `Ersatz` im Fahrerplan); eigene `fahrtage` einer
  Tour aus dem Fahrerplan grenzen ein („Montag Nordtour“ ↔ „Nordtour“,
  `importieren_touren.wochentag_im_namen()`).
  Fahrzeuge (ADR 0160): `Fahrzeug.typ` frei mit Vorschlägen, `erstzulassung`, nächster TÜV
  `tuev_bis` (`tuev_stand`: bald fällig ab 60 Tagen vorher / abgelaufen, in Liste und Seite); Papiere als
  `FahrzeugDokument` (verschlüsselt über `privatdateien`, sehen mit `touren.planen` oder
  `touren.fahrten`, ändern nur mit `touren.planen`). Unter „Einrichten“ nur die Liste; anlegen
  und ändern je Fahrzeug auf eigener Seite (`views_fahrten.fahrzeug`/`fahrzeug_neu`, `FahrzeugForm`).
  Verkauft: `Fahrzeug.verkauft_am` = Archiv (`save()` schaltet aus), nie löschen.
  Fahrten (ADR 0151): `Fahrt` je Tour und Tag mit `Fahrzeug` und Kilometerstand bei Abfahrt und
  Ankunft, Regeln nur in `apps/touren/fahrten.py` (`beginnen()`, `beenden()`, `berichtigen()`; wer
  darf, entscheidet `start.darf()`; kein Ort wird geprüft), Fahrtenbuch in `views_fahrten.py`
  (Recht `touren.fahrten`); Namen von Tour und Fahrzeug stehen als Text in der Fahrt.
  Ganzen Tourtag zurücksetzen (ADR 0162): nur über `apps/touren/tourtag.py` (`inhalt()`,
  `zuruecksetzen()` – Fahrt, Lieferscheine, Anfahrten, Zusatzstopps, Meldungen, Tourstart als ein
  Papierkorb-Eintrag; Rechte `touren.fahrten` und `touren.lieferscheine`); neue Daten je Tour und
  Tag dort in `_mengen()` aufnehmen.
  Höherer Stand bei der Abfahrt als bekannt (ADR 0161): `Fahrt.km_vorher`, im Fahrtenbuch als Zeile
  „unbekannt“ (`Fahrt.km_unbekannt`); Fahrzeug und Stand merkt sich `static/js/fahrt_km.js` bis
  zum Beginn im Gerät (localStorage `bintafeln-fahrt-…`).
  Zusatzstopps und Fortschritt (ADR 0156): `Zusatzstopp` je Tour und Tag über `apps/touren/zusatz.py`
  (freie Adresse wird Station; Mannschaft nur an der eigenen Tour, `zusatz.darf()`); `ablauf.halte(tour,
  datum)` reiht sie als ungespeicherten `Halt` mit `h.zusatz` ein – nie `Halt` aus dieser Liste speichern.
  Fortschritt über `anfahrten.fortschritt()`. Lieferscheine sieht nur die Mannschaft der Tour
  (`lieferscheine.darf_sehen()`), das Büro alle.
  Neuer Stopp vom Büro (ADR 0159): `apps/touren/heuler.py` – `Zusatzstopp.vom_buero` (wer einfügt,
  fährt nicht mit), Push an die Mannschaft über `apps.core.push`, roter Brief über jeder Seite
  (`Modul.kopfzeile`, `touren/_heuler.html`, `static/js/heuler.js`), bis jemand aus der Mannschaft
  bestätigt (`heuler.gesehen()`); nichts bei Stopps der Mannschaft selbst. Brief und Push – auch
  für Nachrichten – erst, wenn die Fahrt begonnen hat (`heuler.unterwegs()`); `fahrten.beginnen()`
  holt den Push nach (`heuler.nachholen()`, `nachrichten.nachholen()`).
  Nachricht der Fahrdienstleitung an die Mannschaft (ADR 0168): `Tournachricht` je Tour und Tag über
  `apps/touren/nachrichten.py` (`senden()` für heute oder einen kommenden Tag, auch an alle Touren; derselbe rote Brief und
  Push; `gesehen()`; fertige Texte `Kurztext` unter „Einrichten“); Stand je Nachricht unter „Touren heute“.
  Statistik der Touren (ADR 0157): `apps/touren/statistik.py` (`Daten(jahr)`, Abschnitte für
  `statistik/_abschnitt.html`), Kisten → kg über `Gewichte` (`Warengruppe.kiste_kg`, sonst
  `TourenEinstellungen.kiste_kg`); **nie eine Auswertung je Person**. Recht `touren.statistik`.
  Meldungen zum Fahrzeug (ADR 0155): `Fahrzeugmeldung` über `apps/touren/meldungen.py` (melden beim
  Beenden der Tour oder zwischendurch; offene über `Modul.startseite` bei allen mit `touren.fahrten`).
  „Ohne Lieferschein abhaken“ (ADR 0152, 0163): `Anfahrt` je Tour, Station und Tag über
  `apps/touren/anfahrten.py` (Station bleibt stehen, ein Lieferschein gilt auch als angefahren; mit
  Umstand aus der Liste `Umstand` der Tafel und Anmerkung, beides als Text in der Anfahrt); die Tour springt über
  `static/js/tour_aktuell.js` zur nächsten offenen Station.
  Drei Personen und Gast (ADR 0153): eigene/kurzfristige Touren mit `Tour.fahrer`, `beifahrer`,
  `beifahrer2`, `gast` (`personen` folgt daraus, `BesetzungMixin`); Tour aus dem Fahrerplan: Tages-
  besetzung nur über `start.aendern()` (auch Gast auf Beifahrerplätzen, aus der Planung über
  `views_touren.besetzung_aendern`). Am Tag selbst ändert die Mannschaft über den Knopf in der Tour
  (`views_touren.start`; kurzfristige Tour: `MannschaftForm`), nie sich selbst heraus und nur, bis die
  Fahrt begonnen hat. ECO-Plattform: `TourenEinstellungen.eco_link` (nur ein Link).
  Routenvorschau in der Planung (ADR 0154, ergänzt ADR 0147): `ablauf.vorschau()` – Zentrale
  (`TourenEinstellungen.start_ziel`) → Stationen → Zentrale; eingebettete Google-Karte nur mit
  Schlüssel (`karten_schluessel`, verschlüsselt) und erst nach Klick (`static/js/tour_karte.js`,
  Baustein `touren/_karte.html`), sonst nur Link; nie bei den Fahrern. Deren Route endet über
  `ablauf.routen(…, zentrale)` ebenfalls an der Zentrale.
  Lieferscheine (ADR 0149): Regeln nur in `apps/touren/lieferscheine.py`; an jeder Station
  möglich, `Lieferschein.art` Abholung/Abgabe (Abgabe: Spender und Empfänger vertauscht, eigene
  Zahlen in der Statistik, ADR 0165); das PDF ist der
  Lieferschein – einmal erzeugt, verschlüsselt in `Lieferschein.datei`, nie neu berechnet, die
  Unterschrift (`static/js/unterschrift_feld.js`) wird nicht aufbewahrt; Mailtext über
  `lieferscheine.mail_inhalt()` (Platzhalter `{tafel}`, `{station}`, Text + HTML); Versand nur an die
  Station, Speichern geht vor Senden (`mail_fehler`), Versand je Tafel aus / zum Test nur an
  `test_email` / an (`TourenEinstellungen.versand`, Vorgabe aus); Aussehen wie der bekannte Vordruck, fest
  gezeichnet in `apps/touren/vordruck.py` (Logo der Tafel, keine Fußzeile).)
  `tickets` (ADR 0087, Regeln in `apps/tickets/ablauf.py`: wer sieht/bearbeitet, Zuständige je
  Kategorie aus Personen und Rollen, Benachrichtigung über ADR 0086, Frist für erledigte).
  Ausfälle beider: Dauer und „wieder gesund“ (`Ausfall.gesund_ab`: ab dann wieder auf den eigenen Plätzen, außer wo schon Ersatz steht) in
  `apps/core/ausfall.py` (ADR 0085).
  `aushang` (ADR 0080, Aushang-Monitore ohne Anmeldung über den Schlüssel im Link; Seiten bieten
  Module über `Modul.aushang` als `Aushangseite` an, z. B. `apps/dienstplan/aushang.py`; Inhalt in
  `apps/aushang/anzeige.py`, Wechsel, große Ansicht und Dialog in `static/js/aushang.js`; nur Namen
  zeigen; Ändern am Monitor nur mit persönlicher PIN über `apps/aushang/pin.py`, die Rechte prüft
  `Aushangseite.aendern` des Moduls). Arbeitszeit am Monitor stempeln (ADR 0123): Regeln in
  `apps/aushang/stempeln.py` (wo: `an()`, QR-Marke `marke()`/`einloesen()`), mit PIN oder
  wechselndem QR-Code; „nur am Monitor“ über `arbeitszeit.hier_erlaubt()`/`freigeben()`.
  Seite „Fortschritt der Ausgabe“ (ADR 0135) in `apps/aushang/fortschritt.py` (`zahlen()`: Aufruf
  gestartet → aufgerufen/alle, sonst `stelle.fortschritt()`); Folien mit `data-schnell` lädt der
  Monitor alle 20 Sekunden neu.
  `uebernahme` (ADR 0006 ergänzt, ADR 0100, Übernahme aus einem anderen Tafelprogramm; kein
  Herstellername in Oberfläche, Doku oder Code – nur Blatt- und Spaltennamen der Exportdatei):
  reine Umwandlung in `apps/uebernahme/konvertieren.py` (`umwandeln(bytes)` → neutrale Importformat-Dateien),
  herstellerweite Code-Tabellen in `apps/uebernahme/codes.py`, je-Tafel-Zuordnungen (Ausgabestellen,
  Einkommensarten) in `UebernahmeEinstellungen`; die Seite schickt den Kundenstamm direkt in den
  Abgleich (`ImportVorbereitung` → `kunden:import_vorschau`), Anträge/Mitarbeitende als CSV.
  Keine festen Tafel-Werte, keine Personendaten; Tests mit erfundenem Workbook.
  `angebote` (ADR 0131, Angebote mit begrenzten Plätzen wie ein Kochkurs: Regeln in
  `apps/angebote/ablauf.py`, `Interesse` je Person an der Kundennummer, Eintragen nur am Einlass
  über `Modul.einlass`, Höchstzahl schließt die Liste, Plätze nach Reihenfolge).
  `vereinsportal` (ADR 0126, 0128; in Oberfläche und Doku „WISO MeinVerein“, im Code der neutrale
  Name `vereinsportal`): liest Finanzexport-ZIP (Blatt „Spenden -
  Übersicht“) und Liste „Spender mit E-Mail“ in den gemeinsamen Spendenpool ein
  (`apps/vereinsportal/einlesen.py`): je Beleg `Spende` + `Adresse` (Namen über `namen.py`) +
  `SpendenBeleg`. Keine eigenen Belege, Listen oder Dankesbriefe im Modul.
  Versendet in WISO MeinVerein nur über die Spalten `VERSANDSPALTEN` (im Export unter „Erweiterte
  Einstellungen → Spalten“ anzukreuzen; `abruf._versandspalten()` tut das, `einlesen.stand()`
  wertet sie aus: nur echte Daten zählen, nicht der Text „Invalid Date“; ein Beleg ohne Versand in
  der Übersicht nimmt einen früheren Vermerk zurück).
  Automatischer Abruf (ADR 0127): Browser nur im optionalen Dienst `abruf` (`docker/abruf/abruf.py`,
  Compose-Profil `abruf`, Schlüssel `BINTAFELN_ABRUF_SCHLUESSEL`); bintafeln spricht ihn über
  `apps/vereinsportal/abruf.py` an (in Tests `abruf._anfrage` ersetzen), der Ablauf ist gegen eine
  nachgebaute Seite in `tests/e2e/test_abruf_dienst.py` getestet. Zugangsdaten sind persönlich
  (ADR 0129): `Zugang` je Konto, nie fremde anzeigen oder benutzen; eigenes Recht
  `vereinsportal.abruf`; den 2FA-Code gibt nur ein, wer gestartet hat; jeder Abruf steht als
  `Abruf` in der Historie (`abruf.historie()`).
  Hooks `Modul.fristen`, `Modul.auskunft_mitarbeiter`, `Modul.aushang`,
  `Modul.einlass`, `Modul.auskunft_antrag`, `Modul.kopfzeile`, `Modul.seitenleiste`, `Modul.suchen`,
  `Modul.startseite`, `Modul.mein_konto` (persönliche Angaben eines Kontos – PIN, Zugangsdaten,
  Unterschrift – werden nur auf „Mein Konto“ eingetragen, geändert und gelöscht; andere Seiten
  zeigen nur den Stand und verweisen dorthin), `Modul.datenimport` (eigene Übernahmen auf der Seite
  „Daten importieren“ statt eigener Menüpunkte), `Modul.nach_aufnahme` (Weg zurück nach dem
  Aufnahme-Assistenten, z. B. zur Terminliste der Warteliste), `Modul.antrag_status` (der eine Status
  oben auf der Antragsseite, ADR 0139), `Modul.meine_einsaetze` (eigene Einsätze eines Dienstplans als
  Abschnitt der einen Seite „Dienstpläne → Meine Einsätze“ – kein eigener Menüpunkt je Modul). Programmname nur in
  `bintafeln/programm.py`; die Kopfzeile kürzt `static/js/kopfzeile.js` über `.kuerz-1…5`.
  Übersicht der übernommenen Altprogramme: `docs/altprogramme.md`.
- Datenimport aus CSV/Excel (ADR 0078): App `datenimport` – `lesen.py` (CSV/xlsx), `zuordnung.py`
  (Spaltenvorschlag, Vorlagen), `abgleich.py` (neu/Konflikt/Ergänzung/Dublette/fehlt, Wahl je
  Feld, für alle Ziele gleich), Ziele in `ziele.py` (Ausgabestellen, Kundengruppen, Mitarbeitende, Adressbuch,
  Mitglieder, Kundenstamm; Kontobuchungen über `buchungen.csv`, `Buchung.importiert`).
  Neue Ziele dort ergänzen. Kundenstamm: Assistent schreibt ins Importformat um, Ergänzen in
  `apps/kunden/import_ergaenzen.py`; Haushalt in den Papierkorb über `apps/kunden/entfernen.py`.
- Nachtmodus (ADR 0164): `Benutzer.darstellung` (hell/dunkel/wie das Gerät, nur auf „Mein Konto“),
  `data-nacht` am `<html>` (bei „Wie das Gerät“ über `static/js/darstellung.js`); dunkle Farben am
  Ende von bintafeln.css unter `:root[data-nacht]`. In CSS Flächen und Schrift über die Variablen
  (`--flaeche`, `--flaeche-2`, `--text`, `--rand`); eine neue Regel mit fester heller Fläche bekommt
  dort ein dunkles Gegenstück. PDFs, Unterschriftsfelder und Vorschauen bleiben hell.
- Überraschungen auf der Anmeldeseite an Festtagen: `apps/core/anlaesse.py` und
  `templates/includes/anlass.html` (SVG + CSS, kein JavaScript; ADR 0079).
- Serienbriefe (ADR 0047, 0088): Vorlagen-Text und Fußzeile als bereinigtes HTML aus
  `static/js/html_editor.js` (Platzhalter gespeichert als `{name}`, im Editor als Feld über
  `data-platzhalter`, Kärtchen mit `data-platzhalter-karte`; Namen in `empfaenger.NAMEN`).
  Einsetzen (Werte immer maskiert), alte Textvorlagen, HTML→ReportLab und Mail in
  `apps/serienbriefe/gestaltung.py` (`brief()`, `mail()`, `flowables()`); PDF in `brief.py`.
  Live-Vorschau neben dem Editor: `views.vorlage_bild` (erste Seite als PNG über pypdfium2,
  Seitenzahl im Kopf `X-Seiten`), geladen von `static/js/brief_vorschau.js`.
  Grafiken (ADR 0138): `Grafik` + `apps/serienbriefe/grafiken.py` (`speichern()` verkleinert und
  speichert ohne Metadaten neu, `aus_src()` nur eigene Adressen, `fuer_mail()` → `cid:`); im Text
  `<img src="…/grafiken/<pk>/" width="25%|50%|100%">`; Mails mit Bildern über
  `mail.senden(..., bilder=…)`; nie Bilder aus dem Internet abrufen.
  Grafiken frei auf der Seite (ADR 0166, z. B. Unterschriften): `Vorlage.freie_grafiken` (mm ab
  links oben, erste/letzte Seite), Prüfen, Zeichnen und Mail nur über `apps/serienbriefe/frei.py`;
  verschieben in der Vorschau über `static/js/brief_frei.js` (die Live-Vorschau zeichnet sie nicht
  selbst). `grafiken.speichern(..., freistellen=True)` macht Weiß durchsichtig; PDF → erste Seite.
  Empfänger: Quellen in `empfaenger.QUELLEN`/`suchen()` (auch Ehrenamtliche und ehemalige
  Ehrenamtliche wie die Listen unter „Verein/Team“; Quelle `liste`: die im Adressbuch unter „Liste
  zusammenstellen“ gewählten Personen, nur in der Sitzung unter `emp.LISTE_SITZUNG`, nie gespeichert); in der Vorschau jeder Empfänger zum An- und
  Abhaken (`an`, gilt nur zur selben Auswahl: `views._auswahl_kennung()`); abgewählter Haken „nur
  mit Einwilligung“ wird je Konto gemerkt (`Benutzer.listen_filter`).
- Spenden: `Spende.fremdbeleg` (ADR 0128) kennzeichnet Spenden mit Beleg aus einem anderen
  Programm (von Hand an der Spende änderbar; `fremdbeleg_von_hand` schützt das vor dem Einlesen); „versendet“ bekommt nie eine Bestätigung aus bintafeln, „offene“ bestätigt bintafeln
  selbst (eine einzeln, mehrere im Jahr als Sammelbestätigung, dann ohne den fremden Beleg) – die
  Regel steht nur in `bestaetigung.offene_geldspenden()` und `dank._beizulegende()`; Übersicht aller
  Spender eines Jahres in `bestaetigung.spenderuebersicht()`.
  Eingescannte Unterschrift (ADR 0130): `Unterschrift` je Konto (`apps/spenden/unterschrift.py`),
  nie die eines anderen Kontos anzeigen oder benutzen; `bestaetigung.unterschreiben()` nimmt nur
  die der Person, die ausstellt; das unterschriebene PDF liegt als `Ausfertigung` und wird nicht
  neu berechnet (`bestaetigung.pdf()` gibt es aus).
  Aussehen der Bestätigung wie der bekannte Vordruck (ADR 0136): gezeichnet in
  `apps/spenden/vordruck.py` mit festen Maßen (nicht über den `Pdf`-Rahmen), Betrag ziffernweise
  (`vordruck.ziffern()`), Satz zur maschinellen Erstellung nur mit
  `SpendenEinstellungen.maschinell_angezeigt`. Stempel der Tafel (ADR 0137) als
  `SpendenEinstellungen.stempel` (verschlüsselt, `unterschrift.stempel_speichern()`); Unterschrift
  und Stempel werden beim Hochladen freigestellt (`unterschrift.freistellen()`, weiß → durchsichtig).
  Kategorie „Spender“ setzt `Spende.save()` über `adressen.models.als_spender_markieren()` (nur
  hinzufügen, nicht bei `mitgliedsbeitrag`, ADR 0132).
  Spendenentwicklung (Grafiken je Jahr) in `apps/spenden/entwicklung.py`, gezeichnet mit
  `apps/statistik/diagramme.py`, Abschnitte wie in der Statistik (`statistik/_abschnitt.html`).
  Import in `apps/spenden/importieren.py` (ADR 0055, `belegnummer` gegen Dubletten),
  Dankesbriefe und hochgeladene Belege in `apps/spenden/dank.py` (ADR 0056; PDFs zusammenfügen
  mit `pypdf`, Mail-Anhänge über `mail.senden(..., anhaenge=…)`).
- Browser-Tests in `tests/e2e/` (Playwright, ADR 0066): nur mit `pytest -m e2e`, Abhängigkeiten in
  `requirements-e2e.txt`, eigener CI-Job `e2e`. JavaScript-Fehler lassen sie scheitern; neue
  JavaScript-Funktionen dort mit einem Ablauf abdecken.
- Commit-Beschreibungen: Stichpunkte mit „- “ erscheinen auf der Update-Seite unter „Was ist neu?“
  (`aenderungen()` in `docker/updater/updater.sh`), also verständlich für die Tafeln formulieren.
- Shell-Skripte müssen `shellcheck` bestehen. Änderungen an Sicherung oder Wiederherstellung
  deckt `tests/sicherung_e2e.sh` ab (läuft in CI im Job `docker`).
