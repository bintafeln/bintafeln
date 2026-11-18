# 0146: Einkommensart sammelweise ändern

- Status: Angenommen
- Datum: 2026-11-18

## Problem

Nach der Übernahme aus dem bisherigen Programm tragen viele Haushalte eine zu grobe Einkommensart
(z. B. „Sonstiges“). Sie einzeln zu berichtigen ist bei hunderten Haushalten nicht zumutbar. Eine
Sammeländerung für Haushalte gab es nicht.

## Entscheidung

- Seite „Einstellungen → Kunden → Einkommensart sammelweise ändern“
  (`apps/kunden/views_einkommensart.py`, Recht `kunden.bearbeiten`): bisherige Einkommensart,
  Alter der Hauptperson (ab … Jahren, unter … Jahren, egal) und neue Einkommensart wählen.
- Erst ansehen, dann ändern: Die Seite zeigt Zahl und Liste der betroffenen Haushalte; geändert
  wird nur mit „Jetzt ändern“ nach Rückfrage.
- Aktive wie nicht mehr aktive Haushalte; nur Kunden, die das Konto sehen darf (ADR 0034).
- „Ab 65“ heißt: am heutigen Tag 65 Jahre alt oder älter. Haushalte ohne Geburtsdatum der
  Hauptperson bleiben unverändert und werden eigens gezählt.
- Jede Änderung setzt `Haushalt.geaendert_am` und steht in Historie und Änderungsprotokoll. Die
  Regel „ohne gültigen Ausweis keine Kundengruppe“ wird dabei nicht angestoßen: Eine geänderte
  Einkommensart soll niemanden nebenbei aus seiner Gruppe nehmen.
- Viele Haushalte: Die Ansicht arbeitet je Aufruf höchstens 15 Sekunden und lädt sich dann von
  selbst neu (wie das Nachrechnen der Kasse), damit die Seite nicht hängt.

## Begründung

Nichts ist fest eingebaut: Einkommensarten und Altersgrenze wählt die Tafel, die Funktion taugt
damit auch für spätere Umstellungen. Ein Import kann die Einkommensart wieder überschreiben, wenn
die geänderten Haushalte im Abgleich nicht behalten werden; darauf weist das Handbuch hin.
