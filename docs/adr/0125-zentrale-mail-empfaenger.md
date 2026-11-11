# ADR 0125: Wer bekommt welche Mail – eine zentrale Seite

## Problem

Wer eine Mail des Programms bekommt, war über das Programm verstreut und teils gar nicht
einstellbar: Korrekturwünsche vom Einlass und Sicherheitsupdates gingen immer an alle Konten mit
dem passenden Recht (also z. B. an jeden Admin), die Empfänger für neue Anträge standen in den
Antrags-Einstellungen, die für Ausfälle im Fahrdienst in den Fahrdienst-Einstellungen. Eine
Übersicht, welche Mails es überhaupt gibt, wann sie kommen und an wen, fehlte.

## Entscheidung

- **Eine Seite** „Einstellungen → Tafel → Mail-Empfänger“ (`core:mail_empfaenger`, Recht
  `einstellungen.mail`) zeigt jede Mail mit Anlass und Empfängern.
- **Benachrichtigungen an Mitarbeitende** beschreibt weiter `benachrichtigung.Art`, jetzt mit
  `wann` und `an`. Geht eine Mail an eine Gruppe, trägt die Art eine `Empfaengerwahl`
  (`berechtigte()`, `leer`): Die Tafel wählt auf der Seite die Personen aus den Berechtigten.
  Die Auswahl liegt in `MailEmpfaenger` (je Art die Konten).
- **Ohne Auswahl gilt die bisherige Vorgabe** – bei Korrekturwunsch, Sicherheitsupdate und
  Fahrdienst alle mit dem Recht, beim neuen Antrag niemand. Bestehende Installationen verhalten
  sich nach dem Update unverändert.
- **Bestehende Auswahlfelder ziehen nicht um:** `AntragEinstellungen.benachrichtigen` und
  `FahrdienstEinstellungen.benachrichtigen` bleiben, wo sie sind (`Empfaengerwahl.lesen` und
  `.speichern`); nur die Bedienung wandert auf die zentrale Seite. So braucht es keine
  Datenmigration, und eine ältere Version findet die Auswahl nach einem Zurückgehen wieder.
- **„Niemand“ ist eine eigene Wahl** (`MailEmpfaenger.niemand`): Eine leere Auswahl heißt
  „Vorgabe“, also meist alle Berechtigten. Wer eine Mail gar nicht will, setzt den Haken „Niemand
  bekommt diese Mail“; er gilt für alle Mails mit Auswahl, auch für die mit eigener Ablage.
- **Niemand fällt still weg:** Gesperrte Konten und Konten ohne das Recht bekommen nichts mehr.
  Bleibt bei der zentralen Auswahl so niemand übrig, geht die Mail wieder an alle Berechtigten.
- **Alle übrigen Mails** (an Kunden, Spender, einzelne Personen) stehen als `Mail` in
  `apps/core/mailuebersicht.py`, die der Module in `Modul.mails`. Sie werden nur erklärt und
  verlinken dorthin, wo Texte und Einstellungen stehen.
- **Nicht zentralisiert:** die persönliche Häufigkeit (sofort, gesammelt, nie) unter „Mein
  Konto“ (ADR 0086) und Empfänger, die sich aus der Sache ergeben (Teamleitung im Dienstplan,
  Zuständige einer Ticket-Kategorie). Sie werden auf der Seite beschrieben.

## Begründung

Die Frage „Wer bekommt das?“ soll eine Tafel an einer Stelle beantworten und ändern können, ohne
jedes Modul zu kennen. Die Auswahl auf Berechtigte zu beschränken verhindert, dass jemand Mails
über Dinge bekommt, die er im Programm nicht sehen darf. Dass die Mail bei ungültiger Auswahl
wieder an alle geht, ist die sichere Richtung: lieber eine Mail zu viel als ein Korrekturwunsch
oder Sicherheitsupdate, von dem niemand erfährt.
