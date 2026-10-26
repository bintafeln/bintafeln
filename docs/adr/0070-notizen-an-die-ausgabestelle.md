# 0070: Notizen der Verwaltung an die Ausgabestelle

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Ausgabestellen melden der Verwaltung z. B. „Neuen Ausweis drucken“ oder „Bescheid geprüft –
verlängern“ (ADR 0062, 0068). Die Antwort („Ausweis ist gedruckt“) kam bisher nur als Notiz am
Haushalt an; die Ausgabestelle sah sie erst, wenn sie den Kunden aufrief. Gleichzeitig sollen
nicht alle Notizen der Verwaltung bei den Ausgabestellen auftauchen.

## Entscheidung

- `Notiz.an_stelle`: Eine Notiz geht nur auf ausdrücklichen Wunsch an die Ausgabestelle. Das
  geschieht über den Haken beim Schreiben, den Haken bei der Sammel-Verlängerung für nicht
  verlängerte Ausweise oder automatisch beim Ausweisdruck als Antwort auf die Meldung „Neuen
  Ausweis drucken“. Eine Verlängerung selbst schreibt keine Notiz.
- Die Startseite aller, die an der gewählten Ausgabestelle am Einlass arbeiten, zeigt eine solche
  Notiz ganz, mehrere als Link zur Sammelseite. „✓ gelesen“ (`gelesen_am`, `gelesen_von`) nimmt
  sie von der Startseite; am Haushalt bleibt sie mit diesem Vermerk stehen. Logik in
  `apps/kunden/an_stelle.py`.
- Ausweisdruck (einzeln oder Sammeldruck): Für jeden Haushalt mit offener Meldung „ausweis“
  wird die Antwort-Notiz geschrieben, die Meldung erledigt und die gemeldete Notiz gestrichen.
  Der Text richtet sich nach `Ausgabestelle.ausweise_hier`: „… liegt im Schrank“ (z. B.
  Zentrale) oder „… wird zur Ausgabestelle geschickt“.
- Antwort auf eine Nachricht (Nachrichtenliste, Haushaltsseite): Notiz mit `fuer_stelle` = die
  Ausgabestelle, die geschrieben hat; so erreicht sie auch Ausgabestellen, zu denen der Kunde
  nicht gehört. Die Nachricht ist damit erledigt.
- Anliegen, auf die das Programm reagiert (`FESTE_ANLIEGEN`: „verlaengern“, „ausweis“), haben je
  eine feste Notiz-Vorlage, die eine Datenmigration anlegt. Admins können ihren Text ändern,
  aber weder das Anliegen noch die Vorlage löschen. Für neue Vorlagen werden diese Anliegen
  nicht angeboten. Die Anliegen selbst stehen im Code und sind von niemandem änderbar.

## Begründung

Ein Klick weniger und keine verpasste Antwort: Wer den Ausweis druckt, beantwortet damit die
Meldung. Das Programm erkennt die Meldung am festen Anliegen, nicht am freien Text, damit
Missverständnisse ausgeschlossen sind.
