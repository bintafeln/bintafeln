# 0116: Getrennte Nummernkreise für Mitarbeitende und Mitglieder

- Status: Angenommen
- Datum: 2026-11-07
- Ersetzt: ADR 0101 (gemeinsame Personennummern-Reihe)

## Problem

ADR 0101 führte eine **gemeinsame** Nummernreihe für Mitglieds- und Personalnummern ein, damit eine
Person nie zwei Nummern hat und keine Zahl doppelt vorkommt. In der Praxis verwirrt das: Eine
Mitgliedsnummer (z. B. 1) wird abgelehnt, weil die 1 schon als Personalnummer eines Mitarbeitenden
vergeben ist – obwohl Mitgliedsnummer und Personalnummer fachlich verschiedene Dinge sind und sich
nicht in die Quere kommen sollten.

## Entscheidung

- Mitgliedsnummern und **Personalnummern** sind **unabhängige Nummernkreise**. Dieselbe Zahl darf in
  beiden vorkommen (eine Mitgliedsnummer 1 und eine Personalnummer 1 sind erlaubt).
- Jeder Kreis hat seinen eigenen Zähler: Mitgliedsnummern aus `MitgliederEinstellungen.naechste_nummer`
  (`mitglieder.naechste_nummer()`), Personalnummern aus `PersonalEinstellungen.naechste_personalnummer`
  (`verwaltung.naechste_personalnummer()`). Beim Anlegen eines Mitarbeitenden wird die nächste freie
  Personalnummer automatisch vergeben – unabhängig davon, ob die Person auch Mitglied ist.
- **Keine Kreuz-Prüfung mehr:** Eine von Hand gesetzte Mitgliedsnummer wird nicht gegen vorhandene
  Personalnummern geprüft und umgekehrt; jede Nummer muss nur in ihrem eigenen Kreis eindeutig sein.
- **Anzeige:** In der Mitarbeitendenliste gilt die Personalnummer (`verwaltung.personennummer()`),
  auch wenn die Person zugleich Vereinsmitglied ist. Die Mitgliedsnummer steht im Adressbuch.

## Begründung

- Mitgliedsnummer und Personalnummer bezeichnen verschiedene Rollen einer Person. Sie künstlich in
  eine Reihe zu zwingen, kostet mehr Verständnis, als es bringt, und blockiert naheliegende Nummern.
- Jeder Kreis bleibt für sich eindeutig (eigener gesperrter Zähler, überspringt belegte Nummern),
  genau wie der Mitglieder-Zähler schon vorher.

## Folgen

- Eine Datenmigration trägt allen noch nummernlosen aktiven Mitarbeitenden – jetzt auch
  Vereinsmitgliedern – eine Personalnummer aus dem eigenen Kreis nach und setzt den neuen Zähler
  darüber. Nichts wird gelöscht; umkehrbar (der Zähler fällt mit der Feld-Hinzufügung wieder weg,
  vergebene Nummern bleiben).
- Bereits unter ADR 0101 vergebene Personalnummern bleiben gültig; sie waren schon eindeutig.
- Wer von Hand eine Personalnummer setzt (Recht „mitarbeitende.nummer“), muss sie nur gegen andere
  Personalnummern eindeutig halten; der eigene Zähler rückt über die gesetzte Nummer hinaus.
