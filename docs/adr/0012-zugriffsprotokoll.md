# 0012: Zugriffsprotokoll für Kundendaten

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0005

## Problem

Das Änderungsprotokoll (ADR 0005) hält fest, wer Daten geändert hat. Im Snapshot-Betrieb werden
Kundendaten aber fast nur gelesen. Die Tafel muss trotzdem nachvollziehen können, wer welche
Kundendaten angesehen hat, etwa bei einer Beschwerde oder einer Auskunftsanfrage, und vor allem
bei Angaben der besonderen Kategorie (Art. 9 DSGVO).

## Entscheidung

- **Jeder Aufruf** der Detailseite eines Haushalts wird protokolliert: Zeitpunkt, Benutzer,
  Kundennummer und ob dabei Angaben der besonderen Kategorie angezeigt wurden. Inhalte werden
  nicht protokolliert.
- Die Liste und die Suche werden nicht protokolliert. Sie zeigen nur Kundennummer, Name,
  Kundengruppe, Status und Ausweisdatum.
- Das Protokoll hängt an der Kundennummer, nicht am Datensatz, und übersteht deshalb jeden Import.
- Einsehen dürfen es nur Admins.
- Es hat eine eigene **Löschfrist**, einstellbar je Tafel (30 bis 3650 Tage, Vorgabe 365 Tage).

## Begründung

Ein Protokoll nur für Art.-9-Angaben würde gerade die häufigen Abrufe von Anschrift und
Familiendaten nicht erfassen. Ein Jahr reicht, um Beschwerden und Auffälligkeiten nachzugehen,
ohne selbst zu einer dauerhaften Sammlung von Verhaltensdaten der Mitarbeitenden zu werden.
