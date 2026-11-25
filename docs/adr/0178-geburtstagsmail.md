# ADR 0178: Glückwunsch-Mail zum Geburtstag an Mitarbeitende

## Problem

Der Geburtstagsbrief auf der Startseite (ADR 0170) erinnert an die Geburtstage im Team. Gratuliert
wurde danach außerhalb des Programms. Gewünscht ist, dem Geburtstagskind direkt aus dem Brief eine
schön gestaltete E-Mail zu schicken – mit Text, Grafik und Unterschrift der Tafel, aber nie ohne
dass jemand die Mail vorher gesehen hat.

## Entscheidung

- **Der Text kommt aus den Serienbriefen.** Eine Vorlage bekommt dort die **Verwendung**
  „Glückwunsch zum Geburtstag“ (`Vorlage.verwendung`), eine zweite auf Wunsch „Glückwunsch
  nachträglich“. Je Verwendung gilt eine Vorlage, die zuletzt gewählte. Fehlt die nachträgliche,
  gilt die erste. Neuer Platzhalter `{alter}`. Grafiken und Unterschrift wie in jeder Vorlage
  (ADR 0138, 0166).
- **Dritter Knopf im Geburtstagsbrief** und Link im Geburtstagskalender (heute und die letzten
  sieben Tage): „Glückwunsch per E-Mail“. Nur für andere, nie für den eigenen Geburtstag; nur wenn
  eine Vorlage gekennzeichnet ist. Ohne E-Mail-Adresse steht das statt des Knopfs da.
- **Immer erst ansehen:** Der Knopf öffnet eine Seite mit der fertigen Mail (Empfänger, Betreff,
  Text mit eingesetzten Feldern). Betreff und Text lassen sich dort ändern; die Vorlage bleibt
  unberührt. Erst „Senden“ schickt, „Abbrechen“ führt zurück.
- **Danach:** Die Mail steht im Mail-Archiv (ADR 0124) und als Versand bei den Serienbriefen
  (damit in der Auskunft). Für das sendende Konto gilt der Geburtstag als „Gratuliert“.
  `GeburtstagMail` merkt 30 Tage, wer wann geschrieben hat – das sehen alle, die schreiben dürfen,
  damit niemand doppelt schreibt; ein weiteres Senden bleibt möglich.
- **Wer darf:** wer den Geburtstagsbrief zu allen Mitarbeitenden bekommt
  (`mitarbeitende.geburtstagsbrief`) **und** Serienbriefe erstellen darf
  (`serienbriefe.erstellen`). Kein neues Recht.

## Begründung

Die Serienbriefe können Platzhalter, eingebettete Grafiken und Unterschriften bereits; ein
zweiter Editor für Geburtstagstexte wäre doppelte Arbeit. Die Kennzeichnung an der Vorlage braucht
keine Einstellung an anderer Stelle. Kein automatischer Versand: Ein Glückwunsch, den niemand
gelesen hat, ist keiner – und eine Mail an die falsche Person wäre peinlich.
