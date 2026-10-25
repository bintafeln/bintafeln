# 0053: Wetter in der Kopfzeile und Programmname

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Am Einlass und im Büro ist die Außentemperatur an der Ausgabestelle nützlich (Wartende draußen,
Kühlware). Außerdem soll der Programmname in der Kopfzeile stehen; der endgültige Name ist noch
nicht entschieden. Die Kopfzeile muss auf schmalen Bildschirmen trotzdem lesbar bleiben.

## Entscheidung

- Zuschaltbares Modul `wetter` (ADR 0049), Vorgabe aus. Neuer Modul-Hook `kopfzeile`: eine
  Vorlage, die rechts in der Kopfzeile erscheint und ihren Inhalt per HTMX nachlädt.
- Quelle Open-Meteo (frei, ohne Schlüssel, Daten u. a. vom DWD, CC BY 4.0). Der Server fragt an,
  nie der Browser; übermittelt werden nur PLZ und Ort der Ausgabestelle. Koordinaten und letztes
  Wetter stehen in `WetterStand` (nicht in der Datensicherung). Höchstens alle 30 Minuten je
  Ausgabestelle, nach einem Fehler 10 Minuten Pause, Wetter älter als 3 Stunden wird nicht gezeigt.
- Ort: die Ausgabestelle, der die Person zugeordnet ist, sonst die erste aktive mit PLZ oder Ort.
- Programmname und Untertitel nur in `bintafeln/programm.py`; Code, Adressen und Dateien heißen
  weiter `bintafeln`.
- Die Kopfzeile kürzt sich selbst (`static/js/kopfzeile.js`): Bricht sie um, werden nacheinander
  Untertitel, Wettertext, Programmname, Tafelname (nur mit Logo) und das Wort „Menü“
  ausgeblendet. Ohne JavaScript bricht die Zeile wie bisher einfach um.

## Begründung

Ohne Schlüssel und Vertrag kann jede Tafel das Modul sofort nutzen; wer keine Verbindung nach
außen möchte, lässt es aus. Abruf im Server mit Zwischenspeicher hält die Anfragen gering und
verrät dem Dienst weder Personen noch Geräte der Mitarbeitenden. Ein Name an einer Stelle hält die
Namensfrage offen, ohne Code umbenennen zu müssen.
