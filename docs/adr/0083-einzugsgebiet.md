# 0083: Einzugsgebiet im Antragsformular prüfen

- Status: Angenommen
- Datum: 2026-10-29

## Problem

Manche Tafeln nehmen nur Menschen aus ihrer Stadt auf, anderen ist der Wohnort egal. Anträge von
außerhalb kosten Arbeit, wenn sie erst bei der Aufnahme auffallen.

## Entscheidung

- In „Anträge einstellen“ wählt die Tafel, ob die Anschrift geprüft wird: *nicht prüfen*
  (Vorgabe), *annehmen, aber markieren* oder *nicht annehmen*.
- Das Gebiet besteht aus Postleitzahlen (einzeln oder als Bereich, z. B. `45127-45359`) und/oder
  Orten. Ortsteile mit Bindestrich, Leerzeichen oder Klammer (`Essen-Steele`, `Essen (Ruhr)`)
  passen zum Ort. Ist beides eingetragen, muss beides passen.
- *Nicht annehmen* zeigt im Formular am Feld PLZ eine Meldung in der Sprache des Formulars
  (`fehler_gebiet` mit dem Namen des Gebiets). *Markieren* kennzeichnet den Antrag in Liste,
  Ansicht und Aufnahme-Assistent; berechnet wird das mit den aktuellen Einstellungen, also auch
  für ältere Anträge.
- Die Regel steht als reine Funktion in `apps/antraege/gebiet.py`.

## Begründung

PLZ und Ort reichen, um Anträge von außerhalb zu erkennen. Ob es eine Anschrift wirklich gibt,
ließe sich nur über einen fremden Dienst (Geokodierung) prüfen; dorthin sollen Anschriften
Antragstellender nicht gehen. Die Vorgabe „nicht prüfen“ ändert nichts für Tafeln, die kein
Gebiet haben.
