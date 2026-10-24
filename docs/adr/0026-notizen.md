# 0026: Notizen zum Haushalt

- Status: Angenommen
- Datum: 2026-10-24

## Problem

Am Einlass fällt manches auf, das die nächste Schicht wissen sollte (z. B. „bringt Nachweis
nächste Woche“). Die internen Anmerkungen kommen aus dem Altsystem, sind nur für Büro und Admin
gedacht und werden bei jedem Import ersetzt. Außerdem soll die Rolle Ausgabe nur sehen, was
sie für die Ausgabe braucht.

## Entscheidung

- Neues Modell `Notiz` (Text, Zeitpunkt, verfasst von). Ausgabe, Büro und Admin schreiben
  Notizen, auf der Haushaltsseite oder am Einlass; löschen dürfen Büro und Admin.
- Notizen hängen an der **Kundennummer**, nicht am Haushalt-Datensatz. Der Import (Vollaustausch)
  lässt sie deshalb stehen. Gibt es die Kundennummer nach einem Import nicht mehr, werden sie
  gelöscht, ebenso beim Löschen des Haushalts; ändert der Admin die Kundennummer, ziehen sie mit.
- Notizen stehen in der Auskunft nach Art. 15 und im Änderungsprotokoll.
- Die Rolle **Ausgabe** sieht auf der Haushaltsseite und am Einlass nur: Kundennummer,
  Haushaltsgröße, alle Personen des Haushalts und die Abholberechtigten mit Name und
  Geburtsdatum, Ausgabestelle, Karte gültig bis, Kontostand (abschaltbar), aktive Sperren,
  letzte Abholungen, Notizen und die für sie freigegebenen Zusatzfelder. Anschrift, Kontakt,
  Staatsangehörigkeit, Familienstand, Ausnahmen und interne Anmerkungen nicht.

## Begründung

Datensparsamkeit: Wer ausgibt, braucht keine Anschrift. Notizen sind Daten aus bintafeln und
sollen einen Import überstehen; über die Kundennummer bleiben sie dem richtigen Haushalt
zugeordnet, ohne den Import zu verändern.
