# Fachkonzept: Kundenstamm, Neuanmeldung, Ausgabe

Dieses Dokument beschreibt, **was** bintafeln für die Module 2 bis 4 können soll. Es ist aus der
Praxis von Tafeln abgeleitet und die Grundlage für die Pull Requests dieser Module. Wie die Daten
importiert werden, steht in [importformat.md](importformat.md).

Alle hier genannten Listen, Felder und Fristen sind **Einstellungen je Tafel** in der Datenbank.
Im Code stehen höchstens neutrale Vorgaben. Eine neue Installation hat keine Kunden, keine
Kundengruppen und keine Zusatzfelder, bis die Tafel sie anlegt oder importiert.

## Grundsätze

- **Datensparsamkeit:** Optionale Felder lassen sich je Tafel abschalten. Abgeschaltete Felder
  werden weder angezeigt noch beim Import gespeichert.
- **Löschfristen je Datenart** mit automatischer Löschung. Bintafeln liefert sinnvolle Vorgaben
  statt leerer Felder.
- **Nur zeigen, was gebraucht wird:** Jede Rolle und jede Ansicht (z. B. der Einlass) zeigt nur die
  Angaben, die dort nötig sind.
- **Besondere Kategorien (Art. 9 DSGVO)** wie Gesundheitsdaten werden gekennzeichnet, nur für
  ausdrücklich berechtigte Rollen angezeigt und bei jedem Zugriff protokolliert.

## Modul 2: Kundenstamm

### Haushalt (Kunde)

Ein Haushalt ist die Einheit, die zur Tafel kommt. Er hat eine **Hauptperson** und beliebig viele
**Angehörige**.

| Angabe | Hinweis |
|---|---|
| Kundennummer | eindeutig, wird vom Altsystem übernommen; später vergibt bintafeln sie |
| Status | aktiv, pausiert, gesperrt, beendet |
| Kundengruppe | bestimmt Ausgabestelle, Wochentag und Uhrzeit (siehe unten) |
| Letzter Besuch | Datum der letzten Abholung; nach dem Umstieg aus den Abholungen abgeleitet |
| Kunde seit | Datum |
| Ausweis gültig bis | Ablaufdatum der Berechtigung |
| Einkommensart | aus einer pflegbaren Liste (z. B. Bürgergeld, Grundsicherung, Wohngeld, Rente) |
| Anschrift | Straße und Hausnummer, PLZ, Ort |
| Telefon, E-Mail | je Tafel abschaltbar |
| Kontostand | Stand des Kundenkontos in Euro (im Snapshot aus dem Altsystem; Buchungen folgen mit Modul 4) |

**Nicht** erfasst wird die Höhe des Einkommens. Die Einkommensart genügt als Nachweis.

### Personen (Hauptperson und Angehörige)

| Angabe | Hinweis |
|---|---|
| Anrede, Vorname, Nachname | |
| Geburtsdatum | genaues Datum. Daraus ergibt sich, ob jemand als Kind zählt. Die Altersgrenze („Kind bis … Jahre“) ist eine Einstellung je Tafel. |
| Staatsangehörigkeit | je Tafel abschaltbar |
| Familienstand | je Tafel abschaltbar |
| Zusatzfelder | siehe unten |

### Abholberechtigte

Personen, die für einen Haushalt abholen dürfen: Vorname, Nachname, Geburtsdatum, gegebenenfalls
eigene Kundennummer.

### Sperren und Ausnahmen

- **Sperre:** von, bis (optional), Begründung, eingetragen von.
- **Ausnahme:** Datum, Begründung, eingetragen von. Erlaubt eine Abholung trotz Regel, z. B.
  außerhalb des eigenen Termins (ausgewertet in der Ausgabe, Modul 4).

### Abholungen

Datum, Uhrzeit, Beitrag, Ausgabestelle, eingetragen von. Im Snapshot-Betrieb werden sie aus dem
Altsystem übernommen, ab Modul 4 entstehen sie in bintafeln. Abholungen und Ausnahmen werden nur
für eine **Aufbewahrungsfrist** gespeichert (Einstellung je Tafel, Vorgabe 3 Jahre) und danach
automatisch gelöscht (ADR 0011). Statistiken über längere Zeiträume entstehen aus anonymen
Zählwerten.

### Interne Anmerkungen

Datum, Text, verfasst von. Freitext enthält oft Sensibles. Deshalb sehen ihn nur Admin und Büro,
und er unterliegt einer eigenen Löschfrist.

### Zusatzfelder

Eine Tafel kann eigene Felder anlegen, für Haushalte oder für jede Person (auch Angehörige).

| Eigenschaft | Werte |
|---|---|
| Schlüssel | kurzer technischer Name, z. B. `schwerbehindert`; erscheint im Import als Spalte |
| Bezeichnung | Anzeige, z. B. „Schwerbehindert“ |
| Gilt für | Haushalt oder Person |
| Typ | Ja/Nein, Auswahl (mit pflegbaren Optionen), Text, Datum |
| Besondere Kategorie (Art. 9) | ja/nein. Bei „ja“: Anzeige nur für ausgewählte Rollen, jeder Zugriff wird protokolliert, Hinweis auf die nötige ausdrückliche Einwilligung. |

Beispiele:

- „Schwerbehindert“: gilt für Personen, Typ Auswahl, besondere Kategorie: ja (Gesundheitsdaten).
- „Essgewohnheiten“: gilt für Haushalt oder Person, Typ Auswahl (z. B. keine Einschränkung,
  vegetarisch, ohne Schweinefleisch). Besondere Kategorie: ja, sobald die Optionen auf die
  Religion schließen lassen.

### Kundengruppen und Ausgabestellen

Eine Kundengruppe ist ein fester Abholtermin:

| Angabe | Hinweis |
|---|---|
| Kürzel, Name | |
| Ausgabestelle | Ort der Ausgabe |
| Wochentage, Uhrzeit | |
| Maximum | höchstens so viele Haushalte (für Warteliste und Zuteilung) |
| aktiv | deaktivierte Gruppen bleiben für die Historie erhalten |
| Farbe | optional, zur schnellen Erkennung am Einlass |

### Dokumente

Im Altsystem gespeicherte Dokumente werden **nicht** übernommen. Bintafeln soll Dokumente zu einem
Haushalt aber **speichern können** (z. B. Bescheide, Erklärungen, Datenschutzeinwilligung):

- Kategorie bzw. Dokumentart aus einer pflegbaren Liste
- Dokumentdatum, hochgeladen von, hochgeladen am
- **Aussonderungsfrist je Dokumentart**, danach automatische Löschung
- nie öffentlich abrufbar, nur nach Anmeldung und mit Berechtigung; jeder Abruf wird protokolliert

### Historie

Was sich an einem Haushalt geändert hat: neu aufgenommen, Status, Kundengruppe, Ausweis verlängert,
Personen hinzugekommen oder entfallen. Im Snapshot-Betrieb entsteht die Historie aus dem Vergleich
zweier Importe.

### Daten, die bintafeln schon im Snapshot-Betrieb selbst führt

Der Kundenstamm selbst wird bei jedem Import ersetzt (ADR 0006). Einige Daten entstehen aber in
bintafeln selbst und dürfen beim Import **nicht** verloren gehen: Dokumente, Zugriffsprotokoll,
Historie. Sie hängen an der **Kundennummer**, nicht an internen Datenbank-IDs. Verschwindet eine
Kundennummer aus dem Import, greifen für diese Daten die Löschfristen.

### Rechte

| Rolle | Kundenstamm |
|---|---|
| Admin, Büro | alles lesen, importieren, Dokumente verwalten |
| Ausgabe | nur das, was die Ausgabe braucht: Kundennummer, Name, Status, Kundengruppe, Haushaltsgröße (Erwachsene/Kinder), Ausweis gültig bis, aktive Sperren |
| Kiosk | kein Zugriff auf den Kundenstamm, nur die Kiosk-Ansicht (Modul 4) |

Zusatzfelder der besonderen Kategorie sieht nur, wer dafür ausdrücklich berechtigt ist.

Die Rolle Ausgabe sieht außerdem die letzten fünf Abholungen und die Ausnahmen eines Haushalts.

### Zugriffsprotokoll

Jeder Aufruf der Detailseite eines Haushalts wird protokolliert: wer, wann, welche Kundennummer
und ob dabei Angaben der besonderen Kategorie angezeigt wurden. Einsehen dürfen es nur Admins.
Es hat eine eigene Löschfrist (Vorgabe 1 Jahr, ADR 0012). Liste und Suche werden nicht
protokolliert.

### Auskunft

Auf Anfrage einer Person werden alle zu ihr gespeicherten Daten als PDF zusammengestellt
(Art. 15 DSGVO). Umgesetzt für Haushalte und Mitarbeitende (ADR 0021).

## Modul 3: Neuanmeldung und Warteliste

**Umgesetzt (ADR 0024):** Online-Antrag in 29 Sprachen, Bestätigung per Bildschirm und Mail,
Bearbeitung, Fristen, Missbrauchsschutz, CSV-Export. Die Abarbeitung der Warteliste und die
Zuteilung zu Kundengruppen bleiben vorerst in einem eigenen Programm der Tafel.

- **Online-Antrag** als öffentliches Formular, das eine Tafel in ihre Webseite einbinden kann.
  Modus: Neuantrag, Verlängerung oder beides.
- Je Feld einstellbar, ob es abgefragt wird: Kundennummer (bei Verlängerung), gewünschte
  Wochentage und Ausgabestelle, Anrede, Anschrift, Familienstand, Staatsangehörigkeit, Telefon,
  E-Mail, Angehörige mit Namen und Geburtsdatum, Anhänge (Bescheide), Nachricht.
- Einleitungstext und Bestätigungstext frei gestaltbar und **mehrsprachig**; Links zu
  Datenschutzerklärung und Impressum der Tafel.
- Benachrichtigung ausgewählter Mitarbeitender bei neuen Anträgen.
- **Fristen:** Anträge gelten nach N Tagen als erledigt, werden nach N Tagen in den Papierkorb
  verschoben und nach N Tagen gelöscht.
- **Warteliste** und Zuteilung zu Kundengruppen bis zu deren Maximum.
- Schutz des öffentlichen Formulars vor Missbrauch (z. B. Begrenzung der Anfragen), Uploads nur in
  erlaubten Formaten und Größen.

## Modul 4: Ausgabe

**Umgesetzt (erste Stufe, ADR 0013):** Einlass mit Kundennummer-Scan, Ampel mit den Regeln
unten, Abholung eintragen (mit vorgeschlagenem Beitrag) und am selben Tag zurücknehmen,
Ausnahme für heute erteilen (Admin, Büro). Einstellbar: Höchstzahl Abholungen je Kalenderwoche,
14 Tagen oder Kalendermonat; „heute nicht dran“ rot oder gelb; Vorwarnzeit für den Ausweis;
Beitrag je Abholung, je Erwachsenem und je Kind; Anzeige des Kontostands. Eine Ausnahme für
heute hebt die Terminregeln auf (nicht dran, Höchstzahl, Kundengruppe, Ausgabestelle), nicht
aber Sperre, Status oder abgelaufenen Ausweis.

**Kundenkonto (ADR 0014):** Buchungen mit Soll, Haben und Barbetrag. Zahlweisen je Abholung:
aus Guthaben (Rest bar), alles bar oder, wenn erlaubt, anschreiben. Einzahlungen und
Vorauszahlungen mit erklärtem Vorschlag für den Rest des Monats und den nächsten Monat.
Korrekturen durch Admin und Büro.

**Kasse:** Tages- (je Ausgabestelle), Monats- (je Tag) und Jahresstände (je Monat), rückwirkend
wählbar und nach Ausgabestelle filterbar. Grundlage sind allein die Buchungen.

- **Einlass/Kiosk-Ansicht:** Kundennummer per Scanner (arbeitet als Tastatur) oder Suche.
- Je Tafel einstellbar, was am Einlass sichtbar ist: Adresse, Geburtsdatum, letzte Abholungen,
  Beitrag, Personenanzahl (gesamt/Kinder), aktive Sperren, Farbe der Kundengruppe, Kundenkonto.
- **Ampel** mit einstellbaren Meldungstexten:
  - rot: Ausweis gesperrt, bereits abgeholt, Ausweis abgelaufen, Abholung in dieser Woche nicht
    erlaubt, maximale Abholungen je Woche bzw. je zwei Wochen überschritten, Ausgabestelle nicht
    erlaubt, heute nicht dran, Kundengruppe fehlt
  - gelb: Ausgabestelle nicht vorgesehen, Ausweis läuft bald ab (Vorwarnzeit in Tagen), heute
    nicht dran (wenn nur Hinweis)
  - grün: Ausweis gültig, Ausnahme erteilt
- **Notiz-Knöpfe** mit vorgefertigten Texten (z. B. „Bescheide geprüft, kann verlängert
  werden“).
- **Abholungen:** Datum, Uhrzeit, Ausgabestelle, Beitrag, eingetragen von.
- **Beiträge:** pro Erwachsenem und pro Kind oder gestaffelt nach Haushaltsgröße.
- **Kundenkonto:** Soll/Haben je Abholung, optional Einzahlungen und Guthaben.
- **Status „aktiv“** wird nach dem Umstieg aus den Abholungen abgeleitet (aktiv = in den letzten
  N Tagen abgeholt).
- **Kundenausweis:** Gültigkeitsdauer, fortlaufende Kundennummern, Ausdruck als PDF.
- **Sonderaktionen** (z. B. Gutscheine) mit Zeitraum, Auswahlmöglichkeiten und Teilnahmen.

## Offene Punkte

- Ob und wann der Anbieter des Altsystems einen vollständigen Export liefern kann. Bis dahin
  genügt eine Liste der aktiven Haushalte (siehe Importformat, Minimalfall).
