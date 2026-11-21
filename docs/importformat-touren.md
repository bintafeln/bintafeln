# Importformat für die Stationen und Touren

Version 1.1

| Version | Änderung |
|---|---|
| 1.1 | neue Datei `tourstationen.csv` (Stationsfolge je Tour, ADR 0148). `stationen.csv` unverändert. |
| 1 | erste Fassung: `stationen.csv` (ADR 0147) |

Mit diesem Format liest das Modul **Touren** die Stationen der Abholtouren ein: Märkte,
Bäckereien, Lieferanten, Lager, Ausgabestellen und Einrichtungen. Es ist unabhängig von jedem
Altsystem; Werkzeuge, die Daten aus einem bestimmten System in dieses Format bringen, gehören
nicht in das bintafeln-Repository (ADR 0006).

Beispieldateien mit erfundenen Daten: [beispiele/touren/](beispiele/touren/)

## stationen.csv

### Grundsätze

- Eine Datei `stationen.csv`: UTF-8 (mit oder ohne BOM; ersatzweise Windows-1252), Trennzeichen
  Semikolon, erste Zeile mit den Spaltennamen (Kleinschreibung, Reihenfolge beliebig).
- Werte mit Semikolon, Anführungszeichen oder Zeilenwechsel stehen in doppelten
  Anführungszeichen; ein Anführungszeichen im Wert wird verdoppelt.
- **Die `kennung` entscheidet:** Gibt es eine Station mit dieser Kennung, wird sie aktualisiert,
  sonst neu angelegt. Die Kennung muss deshalb bei jedem Import dieselbe sein (z. B. die Nummer
  aus dem bisherigen System).
- **Leere Zellen ändern nichts.** Beim Aktualisieren überschreiben nur gefüllte Zellen; fehlende
  Spalten ebenso wenig. Eine leere Zelle heißt „unbekannt“, nicht „löschen“.
- **Fehlende Stationen bleiben.** Der Import löscht nie. Wird eine Station nicht mehr
  angefahren, `aktiv` auf `nein` setzen.
- Zeilen mit Fehlern werden übersprungen und im Prüfbericht mit Zeilennummer genannt; übernommen
  wird erst nach dem Prüfbericht.
- Unbekannte Spalten werden ignoriert und im Prüfbericht genannt. Höchstens 5000 Zeilen.
- „CSV herunterladen“ in der Liste der Stationen schreibt genau dieses Format.

### Spalten

| Spalte | Pflicht | Inhalt |
|---|---|---|
| `kennung` | ja | eindeutig und dauerhaft, höchstens 60 Zeichen |
| `art` | ja | `markt`, `baeckerei`, `lieferant`, `lager`, `ausgabestelle`, `einrichtung` oder `sonstiges` |
| `name` | ja | Anzeigename, höchstens 150 Zeichen |
| `kette` | nein | Name der Kette, z. B. der Supermarktkette |
| `filialnummer` | nein | Markt- oder Filialnummer |
| `strasse` | ja | Straße ohne Hausnummer |
| `hausnummer` | nein | z. B. `12a` |
| `plz` | ja | Postleitzahl (vier oder fünf Ziffern) |
| `ort` | ja | |
| `ortsteil` | nein | |
| `telefon` | nein | |
| `email` | nein | allgemeine E-Mail der Station |
| `email_lieferschein` | nein | Adresse für Lieferscheine; leer = `email` |
| `ansprechpartner` | nein | geschäftlicher Kontakt in der Station |
| `oeffnungszeiten` | nein | Freitext |
| `abholtage` | nein | Wochentage mit Komma: `Mo, Di, Mi, Do, Fr, Sa, So` (auch ausgeschrieben) |
| `abholzeit` | nein | Freitext, z. B. `ab 7:30` |
| `anfahrt` | nein | Notiz für die Fahrer: Zufahrt, Rampe, Klingel, Parken |
| `lieferschein` | nein | `ja`/`nein`; leer bei neuen Stationen = `ja` |
| `aktiv` | nein | `ja`/`nein`; leer bei neuen Stationen = `ja` |
| `breite` | nein | Breitengrad als Dezimalzahl; nur zusammen mit `laenge` |
| `laenge` | nein | Längengrad als Dezimalzahl |
| `notiz` | nein | Freitext |

Die Navigation nutzt die Anschrift. `breite` und `laenge` sind nur nötig, wenn die Anschrift
nicht zur richtigen Zufahrt führt; sind sie gesetzt, gelten sie.

## tourstationen.csv

Welche Stationen jede Tour in welcher Reihenfolge anfährt. Wird getrennt eingelesen („Touren
planen → Importieren“), nach `stationen.csv`.

### Grundsätze

- Gleiche Dateiform wie oben. Je Zeile eine Station auf einer Tour.
- **Je Tour ersetzt die Datei die ganze Stationsfolge.** Touren, die in der Datei nicht
  vorkommen, bleiben unverändert. Der Import löscht keine Touren und keine Stationen.
- Touren werden über ihren Namen gefunden (Groß-/Kleinschreibung egal; nur regelmäßige Touren,
  keine kurzfristigen). Unbekannte Touren werden als eigene Tour angelegt; gibt es im Fahrerplan
  eine Tour mit demselben Namen, wird die neue Tour mit ihr verbunden.
- Stationen werden über ihre `kennung` gefunden; unbekannte Kennungen sind ein Fehler der Zeile.
- Eine Station steht je Tour höchstens einmal.

### Spalten

| Spalte | Pflicht | Inhalt |
|---|---|---|
| `tour` | ja | Name der Tour, höchstens 80 Zeichen |
| `reihenfolge` | ja | ganze Zahl ab 1; sortiert die Stationen der Tour (Lücken sind erlaubt) |
| `station` | ja | `kennung` aus `stationen.csv` |
| `wochentage` | nein | an welchen Tagen die Station auf dieser Tour angefahren wird; leer = an allen Fahrtagen der Tour |
