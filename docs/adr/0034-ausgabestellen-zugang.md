# 0034: Mitarbeitende einer Ausgabestelle sehen nur deren Kunden

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Mitarbeitende einer Ausgabestelle sollen nicht alle Kunden der Tafel aufrufen können, nur die
eigenen. Wer an einen fremden Kunden gerät, muss verstehen, warum er ihn nicht sieht.

## Entscheidung

- Konten bekommen eine Zuordnung zu Ausgabestellen (`Benutzer.ausgabestellen`).
- Zugeordnete Konten sehen nur Haushalte, deren Kundengruppe zu einer dieser Ausgabestellen
  gehört. Ohne Zuordnung oder mit dem Recht `kunden.alle_ausgabestellen` (Admin immer, Büro als
  Vorgabe) gilt keine Einschränkung.
- Geprüft wird zentral in `apps/kunden/zugang.py`: Einzelne Haushalte über `zugang.haushalt()`
  (403 mit Begründung auf der Seite „Kein Zugriff“), Listen über `zugang.filtern()`, Daten an
  einer Kundennummer (Notizen, Dokumente) über `zugang.pruefen_nummer()`.
- Der Einlass zeigt statt der Ampel eine Karte mit der Begründung und schreibt keinen Zugriff
  ins Protokoll, weil keine Daten angezeigt werden.

## Begründung

Eine Prüfung an einer Stelle ist leichter zu testen und zu erweitern als verstreute Abfragen.
Die Begründung nennt beide Ausgabestellen und wohin man sich wenden kann, damit am Einlass niemand
ratlos bleibt.
