# 0091 – Abholungen nachtragen

## Problem

Fällt am Einlass die Technik aus, schreiben die Mitarbeitenden die Kunden auf Papier. Diese
Abholungen und Beiträge müssen hinterher in bintafeln, oft erst am nächsten Tag und meist für viele
Kunden einer Ausgabestelle auf einmal.

## Entscheidung

- Seite „Ausgabestelle → Abholungen nachtragen“ (`apps/ausgabe/nachtragen.py`,
  `views_nachtragen.py`): Tag und Ausgabestelle wählen, Liste aller aktiven Haushalte der
  Kundengruppen, die an dem Tag dran waren (`ausgabetag.gruppen_am`), dazu die schon
  eingetragenen. Je Zeile Haken und Betrag (vorbelegt mit `beitrag_fuer` an dem Tag), dazu ein
  Feld für einzelne Kundennummern.
- Der Betrag gilt als bar gezahlt; gebucht wird wie am Einlass über `konto.abholung_buchen` mit dem
  Tag der Abholung, damit die Kasse dieses Tages stimmt. `Abholung.nachgetragen` markiert sie,
  ohne Uhrzeit.
- Die Ampel wird für den gewählten Tag geprüft (`ampel.bewerten`). Recht `einlass.nachtragen`
  (Ausgabe, Büro): nur heute und gestern, eigene Ausgabestellen (`zugang.filtern`), nicht bei Rot.
  Recht `einlass.nachtragen_alle` (nur Admin): jeder vergangene Tag, auch Rot.
- Schon eingetragene Haushalte sind in der Liste nicht anhakbar; ein doppelt abgeschicktes
  Formular bucht nichts doppelt.

## Begründung

Die Papierliste entspricht der Liste des Ausgabetags, deshalb ist Anhaken schneller als jede
Kundennummer einzeln. Die Zeitgrenze und das Verbot bei Rot verhindern, dass am Einlass im
Nachhinein Regeln umgangen werden; Ausnahmen bleiben beim Admin.
