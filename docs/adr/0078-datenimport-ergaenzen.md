# 0078: Datenimport mit Zuordnung, Ergänzen und Konfliktlösung

- Status: Angenommen
- Datum: 2026-10-27
- Ergänzt: ADR 0006 (Importformat), 0028 (Import-Abgleich)

## Problem

Bisher gab es nur einen Weg, Daten zu übernehmen: den Kundenstamm als CSV-Dateien im eigenen
Importformat, und jeder Import ersetzte den ganzen Bestand. Tafeln haben ihre Daten aber in sehr
verschiedenen Dateien (Excel-Listen mit Titelzeilen, eigene Spaltennamen, Komma statt Semikolon,
Windows-Zeichensatz). Außerdem sollen Ausgabestellen und Mitarbeitende mit Anschrift übernommen
werden. Und wer schon Daten in bintafeln hat, möchte neue dazuspielen, ohne die alten zu
verlieren, und bei Unterschieden selbst entscheiden.

## Entscheidung

- Neue App `datenimport` (kein zuschaltbares Modul, gehört zum Kern) mit Import-Assistent:
  1. **Lesen** (`lesen.py`): CSV mit erkannter Kodierung (UTF-8, Windows-1252) und erkanntem
     Trennzeichen, Excel `.xlsx` über `openpyxl` (jedes Blatt eine Tabelle), Kopfzeile automatisch
     gefunden und änderbar.
  2. **Zuordnen** (`zuordnung.py`): Vorschlag je Spalte aus Schlüssel, Bezeichnung, Synonymen und
     ähnlicher Schreibweise; mehrere Spalten auf ein Feld werden verbunden; Hilfsfelder teilen
     „Name“ und „PLZ Ort“. Zuordnungen lassen sich als `ImportVorlage` speichern und werden
     wieder vorgeschlagen. Nicht zugeordnete Spalten werden nicht übernommen.
  3. **Abgleich** (`abgleich.py`, für alle Ziele gleich): neu, Unterschiede je Feld
     („Konflikt“ = beide gefüllt und verschieden, „Ergänzung“ = bisher leer), unverändert, nicht
     mehr in der Datei, mehrfach in der Datei (zusammengeführt, Widersprüche markiert).
     Unsichere Treffer (z. B. nur gleicher Name) sind „mögliche Dubletten“ und werden nie still
     zusammengeführt. Leere Zellen überschreiben nie etwas.
  4. **Art des Imports**: nur neue hinzufügen, hinzufügen und aktualisieren, ersetzen. Die Art
     setzt nur die Voreinstellungen; jede Wahl (Feld übernehmen, Dublette, was mit fehlenden
     geschieht) ist einzeln änderbar.
- Ziele in `ziele.py`: **Ausgabestellen** (fehlende: behalten, inaktiv, löschen über den
  Papierkorb; bei Verweisen nur inaktiv), **Mitarbeitende** (Konto plus Stammdaten mit Anschrift;
  neue Konten ohne Passwort; Treffer über Benutzername, E-Mail oder Name und Geburtsdatum;
  fehlende nur sperren, nie löschen, ADR 0015; Rollen nur für neue Konten und nur vergebbare),
  **Kundenstamm**.
- Der **Kundenstamm** bleibt beim eigenen Importformat: Der Assistent schreibt die zugeordneten
  Tabellen in dieses Format um und prüft mit `importieren.pruefen()`. Nach der Prüfung wählt man
  zusätzlich zum Vollaustausch „nur neue“ oder „hinzufügen und aktualisieren“
  (`apps/kunden/import_ergaenzen.py`, Vorgabe: aktualisieren). Verglichen wird nur, was die Datei
  liefert. Ein anderer Kontostand wird über `konto.korrigieren()` gebucht (ADR 0014),
  gewählte Löschungen gehen in den Papierkorb (ADR 0073). Beim Vollaustausch lässt sich jetzt jeder
  entfallene Haushalt einzeln behalten.
- Hochgeladene Daten liegen höchstens zwei Stunden als `ImportSitzung` in der Datenbank, nicht in
  der Datensicherung. `ImportLauf.art` hält fest, welche Art ein Kundenimport hatte.

## Begründung

Eine Zuordnung in der Oberfläche ist für Tafeln einfacher als Dateien vorher umzubauen, und die
Prüfung bleibt dieselbe wie beim offenen Importformat (eine Stelle für die Regeln). Ein
gemeinsamer Abgleich für alle Ziele sorgt dafür, dass Konflikte überall gleich aussehen und gleich
gelöst werden. „Hinzufügen und aktualisieren“ als Vorgabe löscht nie etwas; der Vollaustausch
bleibt für die Phase, in der das Altsystem führt (siehe Festlegung zum Kundenstamm in CLAUDE.md),
muss aber bewusst gewählt werden.

## Nachtrag: Adressbuch, Mitglieder, Kontobuchungen, große Bestände

- Weitere Ziele im Assistenten: **Adressbuch** (Treffer über E-Mail oder Name und PLZ, Kategorien
  werden ergänzt, nie entfernt; „ja“ bei einer Einwilligung gilt ab heute; fehlende: behalten oder
  löschen, Adressen mit Spenden oder Mitgliedschaft bleiben) und **Mitglieder** (Anschrift im
  Adressbuch, vorhandene Adresse wird weiterverwendet; Treffer über die Mitgliedsnummer; fehlende:
  behalten oder Austritt mit heutigem Datum). Der alte CSV-Import des Adressbuchs bleibt.
- Kundenstamm: neue optionale Datei **`buchungen.csv`** (Importformat 1.4). `Buchung.importiert`
  markiert importierte Buchungen; ein Vollaustausch ersetzt nur diese, in bintafeln gebuchte
  bleiben für die Kasse (ADR 0014). Der Kontostand kommt weiter aus `haushalte.csv`, nur wenn er
  dort fehlt, aus der Summe der Buchungen.
- **In Teilen importieren:** Beim Ergänzen darf `haushalte.csv` fehlen; dann gehören die Zeilen zu
  vorhandenen Haushalten (`daten["nur_ergaenzen"]`, kein Vollaustausch). Abholungen, Ausnahmen,
  Anmerkungen und Buchungen kommen in beiden Ergänzen-Arten dazu, wenn es sie noch nicht gibt;
  nachgereichte Angehörige, Abholberechtigte und Sperren ebenso. Das geschieht mengenweise
  (wenige Abfragen statt mehrerer je Haushalt).
- Grenzen für große Bestände: 300.000 Zeilen und 60 MB je Datei, `DATA_UPLOAD_MAX_NUMBER_FIELDS`
  20.000 (eine Wahl je Feld im Abgleich), gunicorn wartet bis 300 Sekunden.

## Nachtrag: Kundengruppen, Ausstattung der Ausgabestellen

- Neues Ziel **Kundengruppen** (Kürzel, Name, Ausgabestelle per Name, Wochentage, Uhrzeit auch aus
  Texten wie „Freitag 12:30-13:00“, Maximum, Farbe); Treffer über das Kürzel, sonst den Namen.
  Fehlt eine Gruppe in der Datei, lässt sie sich behalten oder auf inaktiv setzen, nie löschen.
- Ausgabestellen haben jetzt Telefon für Kunden, Fax, Plätze, Helfer, Barrierefrei und WLAN; der
  Import füllt sie mit, dazu Ausgabezeiten („Di 13:00; Do 14:00“, nur hinzufügen) und bis zu drei
  Ansprechpartner der Reihe nach.
