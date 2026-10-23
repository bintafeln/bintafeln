# 0010: Kundenstamm: Umfang, Zusatzfelder und eigene Daten im Snapshot

- Status: Angenommen
- Datum: 2026-10-23
- Ergänzt: ADR 0006

## Problem

Für den Kundenstamm war festzulegen, welche Angaben bintafeln führt, wie tafelspezifische
Angaben wie „Schwerbehindert“ abgebildet werden und was mit Daten geschieht, die erst in bintafeln
entstehen, obwohl der Kundenstamm bei jedem Import ersetzt wird.

## Entscheidung

- Umfang und Importformat stehen in `docs/fachkonzept.md` und `docs/importformat.md`. Das Format
  ist bewusst tolerant: Nur `haushalte.csv` mit Kundennummer und Namen ist Pflicht.
- **Genaues Geburtsdatum** für alle Personen, damit die Altersgrenze für Kinder stimmt.
- **Nicht** geführt werden die Höhe des Einkommens und Dokumente aus dem Altsystem.
- **Zusatzfelder** legt jede Tafel selbst an (für Haushalt oder Person, Typ Ja/Nein, Auswahl, Text
  oder Datum). Felder mit Daten besonderer Kategorien (Art. 9 DSGVO, z. B. Schwerbehinderung)
  werden als solche gekennzeichnet: Anzeige nur für berechtigte Rollen, jeder Zugriff protokolliert.
- **Interne Bemerkungen** werden importiert, wenn die Tafel das einschaltet; sichtbar nur für Admin
  und Büro.
- Bintafeln kann **Dokumente** zu Haushalten speichern, mit Aussonderungsfrist je Dokumentart.
- Daten, die in bintafeln selbst entstehen (Dokumente, Historie, Zugriffsprotokoll), hängen an der
  **Kundennummer** und überstehen jeden Import.
- Code und Repository enthalten keine Einstellungen einer bestimmten Tafel. Jede Installation
  startet leer; Listen, Zusatzfelder und Schalter sind Einstellungen in der Datenbank.

## Begründung

- Ein tolerantes Format erlaubt den Start mit einer einfachen Liste der aktiven Haushalte, auch
  wenn das Altsystem keinen vollständigen Export bietet.
- Frei definierbare Zusatzfelder vermeiden tafelspezifische Spalten im Code. Die Kennzeichnung
  nach Art. 9 sorgt dafür, dass sensible Felder nicht versehentlich überall angezeigt werden.
- Ohne Bindung an die Kundennummer gingen Dokumente und Protokolle bei jedem Import verloren.

## Folgen

- Für Zusatzfelder der besonderen Kategorie braucht die Tafel eine Rechtsgrundlage, in der Regel
  eine ausdrückliche Einwilligung. bintafeln weist darauf hin, prüft sie aber nicht.
- Verschwindet eine Kundennummer aus dem Import, werden ihre Dokumente und Protokolle nach den
  jeweiligen Löschfristen entfernt.
