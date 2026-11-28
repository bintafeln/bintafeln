# ADR 0185: Links auf der Startseite sind für Rollen sichtbar

## Problem

Wer eine Kachel sieht, wurde über genau ein Recht aus dem Rechtekatalog eingestellt (ADR 0057).
In der Praxis denkt niemand so: Gefragt ist „nur der Vorstand“ oder „Büro und Vorstand“. Die
passende Zeile in einer langen Liste von Rechten zu finden, war umständlich, mehrere ließen sich
nicht wählen, und ein Recht, das genau die gewünschten Leute haben, gibt es oft nicht.

## Entscheidung

- An der Kachel werden unter „Sichtbar für“ die **Rollen** angehakt (`Link.rollen`, mehrere
  möglich). Nichts angehakt = alle Angemeldeten. Eine der Rollen genügt.
- Admins sehen immer alle Kacheln.
- Die Migration überträgt bestehende Kacheln: Aus dem bisherigen Recht werden die Rollen, die es
  haben; hatte es keine Rolle, bleibt die Kachel bei den Admins.

## Begründung

- ADR 0033 verbietet Rollennamen **im Code**, weil jede Tafel ihre Rollen selbst anlegt. Hier
  wählt die Tafel ihre eigenen Rollen aus der Datenbank; im Code steht kein Name (wie bei den
  Zuständigen der Tickets, ADR 0087).
- Eine Kachel ist nur ein Link. Sie schützt nichts – das Ziel prüft den Zugriff selbst. Es geht
  um Übersicht, nicht um Zugriffsschutz; dafür ist die Rolle die verständlichere Einheit.
