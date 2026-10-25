# 0052: Vertraute Geräte bei der Zwei-Faktor-Anmeldung

- Status: Angenommen
- Datum: 2026-10-25

## Problem

An festen Geräten der Tafel (Einlass-PC, Büro) ist der Zwei-Faktor-Code bei jeder Anmeldung lästig.
Ganz abschalten soll man ihn für Pflicht-Rollen aber nicht.

## Entscheidung

- Ein Admin stellt unter „Einstellungen → Systemsteuerung → Anmeldung und Zwei-Faktor“ ein, wie
  lange ein Gerät vertraut werden darf (`AnmeldeEinstellungen.vertrauen_tage`: aus, 1, 7, 14, 30,
  90 Tage), für alle Rollen gleich. Vorgabe: aus.
- Wer sich mit Code anmeldet, kann „Diesem Gerät … vertrauen“ anhaken. Der Browser bekommt ein
  signiertes, httponly Cookie mit einem Zufallsmerkmal; gespeichert wird nur dessen Prüfsumme
  (`VertrautesGeraet`) und ein Stand des Passwort-Hashes. Das Passwort bleibt immer nötig.
- Ungültig nach Ablauf, nach Passwortänderung, nach neuer Einrichtung oder Zurücksetzen der
  Zwei-Faktor-Anmeldung, beim Entfernen unter „Mein Konto“ oder durch einen Admin bei
  „Mitarbeitende“; „aus“ entfernt alle. Nicht in der Datensicherung, aber in der Auskunft.

## Begründung

Bequemer Alltag an Geräten der Tafel, ohne die zweite Stufe für fremde Geräte aufzugeben. Ohne
Passwort nützt ein gestohlenes Cookie nichts, und die Datenbank enthält kein verwendbares Merkmal.

## Nachtrag: Anmeldung in zwei Schritten (2026-10-25)

Das Anmeldefenster fragt nur Benutzername und Passwort. Ist ein Zwei-Faktor-Gerät eingerichtet und
der Browser kein vertrautes Gerät, folgt ein eigenes Fenster für den Code (`konten:anmelden_code`,
mit „Diesem Gerät vertrauen“). Zwischen beiden Schritten steht in der Sitzung nur, welches Konto
das Passwort bestanden hat; das gilt 5 Minuten und für 5 Code-Versuche, angemeldet ist man erst
nach dem Code.
