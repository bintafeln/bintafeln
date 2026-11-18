# 0145: Bearbeiten ohne Speichern-Knopf

- Status: Angenommen
- Datum: 2026-11-18
- Ergänzt: ADR 0076

## Problem

Auf den Einstellungsseiten wird jede Änderung sofort gespeichert (ADR 0076). Beim Bearbeiten von
Datensätzen – allen voran dem Haushalt – musste man dagegen weiter „Speichern“ drücken. Wer es
vergaß, verlor die Änderung; wer viel pflegt, drückte den Knopf ständig.

## Entscheidung

- Seiten, die einen **vorhandenen** Datensatz bearbeiten, speichern sofort: das Formular bekommt
  `data-autosave`, der Knopf verschwindet, darunter steht „Änderungen werden sofort gespeichert.“
- Wer etwas **neu anlegt**, drückt einmal „Anlegen“: Ein halb ausgefüllter Datensatz lässt sich
  nicht speichern, solange Pflichtfelder fehlen.
- Knöpfe, die etwas auslösen (Passwort setzen, Update, Sicherung, Aufnahme, Einreichen), und
  alles mit „Löschen“ bleiben Knöpfe.
- Gilt für alle, die die Seite bearbeiten dürfen, nicht nur für Admins.
- Felder, die halb getippt Schaden anrichten, speichern erst beim Verlassen
  (`data-autosave-spaet`, z. B. die Kundennummer). Ändert das Speichern die Adresse der Seite,
  wechselt der Browser dorthin (`data-autosave-folgen`).
- Umstellung in mehreren Schritten: zuerst der Kundenstamm (Haushalt, Personen, Abholberechtigte,
  Sperren, Ausnahmen, Anmerkungen, Listen-Einträge, Zusatzfelder, Buchungen, Sonderaktionen),
  danach Mitarbeitende und Personal, dann die übrigen Seiten und Module. Seiten mit
  Zeilentabellen (z. B. Zeiten einer Ausgabestelle) folgen gesondert, weil dort nach jedem
  Speichern die Zeilen neu geladen werden müssen.

- Dritter Schritt: Spenden, Mitgliedschaften, Sicherungsaufträge, Statistik-Einstellungen und
  die Module (Tickets, Fahrdienst: Springer und feste Besetzung, Dienstplan: Aufgaben, Links,
  Aufruf: Infos, Angebote, Warteliste: Termine, Wochenübersicht: Reihenfolge, Übernahme). Neben
  dem Formular heißt „Abbrechen“ dann „Zurück“.
- Noch offen (eigene Schritte): Seiten mit Zeilentabellen (Ausgabestelle, Antrag bearbeiten,
  Selbstabholer) und Seiten mit Text-Editor und Vorschau (Antragstexte, Serienbrief-Vorlage,
  Rechtstexte, Wartelisten-Texte, Ausweis gestalten).
- Bewusst mit Knopf bleibt die Zeitbuchung („Zeit nachtragen/korrigieren“): Mit Pause wird sie
  als zwei Buchungen gespeichert, ein Speichern je Feld würde Buchungen vervielfachen.

## Begründung

Dasselbe Skript wie bei den Einstellungen; Prüfung, Rechte, Historie und Änderungsprotokoll laufen
unverändert über die bestehenden Ansichten. Folgen: Es gibt kein „Abbrechen“ mehr, und Historie
und Änderungsprotokoll bekommen je geändertem Feld einen Eintrag statt einem je Speichern – der
vorherige Wert bleibt dort nachlesbar.
