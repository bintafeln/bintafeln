# Importformat für den Kundenstamm

Version 1 · Status: Entwurf

Dies ist das **einzige** Format, das bintafeln für den Kundenstamm einliest. Es ist offen
dokumentiert und unabhängig von jedem Altsystem. Werkzeuge, die Daten aus einem bestimmten
Altsystem in dieses Format bringen, gehören nicht in das bintafeln-Repository (ADR 0006).

Beispieldateien mit erfundenen Daten: [beispiele/import/](beispiele/import/)

## Grundsätze

- **Vollaustausch:** Jeder Import ersetzt den gesamten Kundenstamm. Wer in der neuen Datei fehlt,
  ist danach nicht mehr im Kundenstamm. Daten, die bintafeln selbst führt (Dokumente, Historie,
  Zugriffsprotokoll), bleiben über die Kundennummer erhalten (siehe Fachkonzept).
- **Alles oder nichts:** Entweder wird der ganze neue Bestand übernommen oder gar nichts. Ein
  fehlerhafter Import hinterlässt den alten Stand.
- **Erst prüfen, dann übernehmen:** Nach dem Hochladen zeigt bintafeln einen Prüfbericht. Erst nach
  Bestätigung wird importiert. **Fehler** verhindern den Import, **Warnungen** nicht.
- **Sicherung:** Der Import startet nur, wenn die letzte erfolgreiche Sicherung höchstens
  24 Stunden alt ist.
- **Nur aktuelle Kunden:** Übernommen werden sollten nur Haushalte, die aktuell zur Tafel kommen.
  Ehemalige Kunden gehören nicht in den Import (Datensparsamkeit).
- Die hochgeladenen Dateien werden **nicht** aufbewahrt. Protokolliert werden Zeitpunkt, wer,
  Anzahl der Datensätze und eine Prüfsumme.

## Dateien

| Datei | Pflicht | Inhalt |
|---|---|---|
| `haushalte.csv` | **ja** | ein Haushalt je Zeile, mit Hauptperson |
| `personen.csv` | nein | Angehörige (ohne Hauptperson) |
| `abholer.csv` | nein | Abholberechtigte |
| `sperren.csv` | nein | Sperren |
| `bemerkungen.csv` | nein | interne Bemerkungen |
| `kundengruppen.csv` | nein | Kundengruppen mit Ausgabestelle und Termin |

**Minimalfall:** Nur `haushalte.csv` mit Kundennummer, Vor- und Nachname. Alles andere ist
optional und kann später ergänzt werden, sobald vollständigere Daten vorliegen.

Fehlt eine optionale Datei, wird dieser Teil beim Import **geleert** (Vollaustausch). Der
Prüfbericht weist darauf hin, wenn vorher Daten vorhanden waren.

## Allgemeine Regeln

| Regel | Festlegung |
|---|---|
| Zeichenkodierung | UTF-8 (mit oder ohne BOM). In Excel: „Speichern unter“ → „CSV UTF-8 (durch Trennzeichen getrennt)“ |
| Trennzeichen | Semikolon `;`. Felder mit Semikolon oder Zeilenumbruch in doppelte Anführungszeichen setzen |
| Erste Zeile | Spaltenüberschriften genau wie unten (Groß-/Kleinschreibung egal). Reihenfolge beliebig. Unbekannte Spalten → Warnung, werden ignoriert |
| Datum | `TT.MM.JJJJ` oder `JJJJ-MM-TT` |
| Uhrzeit | `HH:MM` |
| Ja/Nein | `ja`/`nein`, `1`/`0`, `wahr`/`falsch` |
| Leere Zelle | Angabe nicht vorhanden |
| Kundennummer | Text, höchstens 20 Zeichen. Führende Nullen bleiben erhalten (`00123` ≠ `123`) |
| Leerzeichen | am Anfang und Ende einer Zelle werden entfernt |

## haushalte.csv

| Spalte | Pflicht | Hinweis |
|---|---|---|
| `kundennummer` | **ja** | eindeutig |
| `nachname` | **ja** | Hauptperson |
| `vorname` | **ja** | Hauptperson |
| `anrede` | | Hauptperson, z. B. Frau, Herr, leer |
| `geburtsdatum` | | Hauptperson |
| `staatsangehoerigkeit` | | Hauptperson |
| `status` | | `aktiv`, `pausiert`, `gesperrt`, `beendet`. Leer = `aktiv` |
| `kundengruppe` | | Kürzel einer Kundengruppe |
| `kunde_seit` | | Datum |
| `ausweis_gueltig_bis` | | Datum |
| `einkommensart` | | Bezeichnung, z. B. „Bürgergeld“. Unbekannte Arten werden angelegt (Warnung) |
| `strasse` | | Straße und Hausnummer |
| `plz` | | |
| `ort` | | |
| `telefon` | | |
| `email` | | |
| `anzahl_erwachsene` | | nur wenn **keine** `personen.csv` geliefert wird; mit Hauptperson |
| `anzahl_kinder` | | nur wenn **keine** `personen.csv` geliefert wird |
| `zusatz_<schluessel>` | | Zusatzfeld, siehe unten. Bei Feldern „gilt für Person“ ist es der Wert der Hauptperson |

## personen.csv (Angehörige)

| Spalte | Pflicht | Hinweis |
|---|---|---|
| `kundennummer` | **ja** | Haushalt, zu dem die Person gehört |
| `nachname` | **ja** | |
| `vorname` | **ja** | |
| `anrede` | | |
| `geburtsdatum` | | ohne Geburtsdatum kann bintafeln nicht zwischen Kind und Erwachsenem unterscheiden (Warnung) |
| `staatsangehoerigkeit` | | |
| `zusatz_<schluessel>` | | Zusatzfelder „gilt für Person“ |

Die Hauptperson steht immer in `haushalte.csv`, nicht hier.

## abholer.csv

| Spalte | Pflicht | Hinweis |
|---|---|---|
| `kundennummer` | **ja** | Haushalt, für den abgeholt werden darf |
| `nachname` | **ja** | |
| `vorname` | **ja** | |
| `geburtsdatum` | | |
| `eigene_kundennummer` | | falls die abholende Person selbst Kunde ist |

## sperren.csv

| Spalte | Pflicht | Hinweis |
|---|---|---|
| `kundennummer` | **ja** | |
| `von` | **ja** | Datum |
| `bis` | | Datum. Leer = unbefristet |
| `begruendung` | | |
| `eingetragen_von` | | Name als Text |

## bemerkungen.csv

| Spalte | Pflicht | Hinweis |
|---|---|---|
| `kundennummer` | **ja** | |
| `datum` | **ja** | Datum |
| `text` | **ja** | mehrzeilig möglich (in Anführungszeichen) |
| `verfasst_von` | | Name als Text |

Ob Bemerkungen überhaupt übernommen werden, ist eine Einstellung je Tafel. Ist sie aus, wird
`bemerkungen.csv` ignoriert (Warnung).

## kundengruppen.csv

| Spalte | Pflicht | Hinweis |
|---|---|---|
| `kuerzel` | **ja** | eindeutig, wird in `haushalte.csv` verwendet |
| `name` | **ja** | |
| `ausgabestelle` | **ja** | Name der Ausgabestelle. Unbekannte werden angelegt |
| `wochentage` | | z. B. `Mo`, `Di,Do`. Erlaubt: Mo, Di, Mi, Do, Fr, Sa, So |
| `uhrzeit` | | Beginn, z. B. `14:30` |
| `maximum` | | höchstens so viele Haushalte |
| `aktiv` | | Ja/Nein, leer = ja |

Fehlt `kundengruppen.csv`, werden Kundengruppen, die in `haushalte.csv` vorkommen, nur mit ihrem
Kürzel angelegt (Warnung). Bestehende Kundengruppen bleiben erhalten.

## Zusatzfelder

Zusatzfelder legt die Tafel **vorher** in bintafeln an (Schlüssel, Bezeichnung, gilt für Haushalt
oder Person, Typ, gegebenenfalls Auswahloptionen, besondere Kategorie). Im Import heißt die Spalte
`zusatz_` plus Schlüssel, z. B. `zusatz_schwerbehindert`.

| Typ | erlaubte Werte |
|---|---|
| Ja/Nein | wie oben |
| Auswahl | eine der eingestellten Optionen (Groß-/Kleinschreibung egal) |
| Text | beliebig |
| Datum | wie oben |

Ein Wert, der nicht passt, wird nicht übernommen (Warnung). Eine Spalte `zusatz_…` ohne angelegtes
Zusatzfeld wird ignoriert (Warnung).

## Prüfbericht

**Fehler** (Import nicht möglich):

- `haushalte.csv` fehlt, oder eine Pflichtspalte fehlt
- Datei nicht in UTF-8 lesbar oder kein Semikolon als Trennzeichen erkennbar
- leere Pflichtangabe in einer Zeile
- doppelte Kundennummer in `haushalte.csv`
- Kundennummer in einer anderen Datei, die es in `haushalte.csv` nicht gibt
- unlesbares Datum in einem Pflichtfeld
- doppeltes Kürzel in `kundengruppen.csv`
- unbekannter Status

**Warnungen** (Import möglich):

- unlesbares Datum in einem optionalen Feld (Angabe wird leer gelassen)
- Geburtsdatum in der Zukunft oder mehr als 120 Jahre zurück (Angabe wird leer gelassen)
- Ausweis abgelaufen
- Angehörige ohne Geburtsdatum
- Kundengruppe, Ausgabestelle oder Einkommensart unbekannt (wird angelegt)
- unbekannte Spalte, unpassender Zusatzfeld-Wert
- optionale Datei fehlt, obwohl vorher Daten dieser Art vorhanden waren
- Angabe zu einem Feld, das die Tafel abgeschaltet hat (wird nicht gespeichert)

Der Bericht nennt zu jeder Meldung Datei und Zeilennummer, aber **keine Inhalte** der Zeile. So
lässt er sich auch weitergeben, ohne Personendaten offenzulegen.

## Nicht Teil des Formats

Bewusst nicht vorgesehen sind: Dokumente und Ausweiskopien, Höhe des Einkommens, Abholungen und
Kundenkonto (folgen mit Modul 4).
