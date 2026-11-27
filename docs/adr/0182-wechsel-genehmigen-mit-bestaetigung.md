# ADR 0182: Genehmigter Wechsel gilt erst mit der Bestätigung des Kunden, Ausweis von selbst

## Problem

Wurde ein Wechselwunsch genehmigt (ADR 0173), zog der Kunde sofort um und bekam nur eine Mail
dazu. Ob er den Wechsel noch will und davon weiß, erfuhr die Verwaltung nicht – zwischen Wunsch
und Entscheidung können Wochen liegen. Außerdem musste jemand daran denken, den neuen Ausweis zu
drucken; es stand nur eine Notiz am Kunden.

## Entscheidung

- **„Genehmigen“ fragt den Kunden.** Er bekommt die Mail „Ihr Wunsch zu wechseln ist genehmigt“
  mit „Ja, ich möchte wechseln“ und „Nein, ich bleibe“. Dahinter steht derselbe Weg wie beim
  Angebot eines Platzes (ADR 0175): Link mit Zufallsschlüssel, gespeichert ist nur die Prüfsumme,
  die Seite zeigt nur den Wechsel, bestätigt wird erst per Knopf, einmal, innerhalb von 7 Tagen.
  **Erst mit dem „Ja“ zieht er um**; so lange ist der Platz reserviert. Die Antwort landet im
  Programm, niemand bekommt dafür eine Mail (`wechsel.genehmigen_und_fragen()`,
  `Wechselwunsch.angebot_genehmigt`).
- Anders als beim Angebot darf die Verwaltung dabei auch **in eine volle Gruppe** genehmigen, und
  es gibt **keine Vorschau** davor: Der Text steht fest.
- **Ohne E-Mail-Adresse** kann niemand bestätigen – dann gilt „Genehmigen“ wie bisher sofort.
  **„Ohne Bestätigung genehmigen“** gibt es daneben für Kunden, die schon zugesagt haben.
- **Der neue Ausweis wird von selbst gemeldet.** Sobald ein Wechsel gilt, legt
  `an_stelle.ausweis_melden()` die Meldung „Neuen Ausweis drucken“ an, als käme sie von der
  Ausgabestelle: Der Kunde steht bei den gemeldeten Ausweisen und geht beim Sammeldruck mit
  (ADR 0167, 0180). Bei einem Wechsel zu einem späteren Datum geschieht das am Stichtag
  (`GeplanterWechsel.ausweis_melden`), weil der Ausweis vorher noch die alte Gruppe zeigte.
  Andere geplante Verlegungen (eine Ausgabestelle schließt) melden nichts.

## Begründung

Eine Bestätigung, die nichts bewirkt, hilft nicht; deshalb hängt der Umzug an ihr. Den sicheren
Weg dafür gab es schon – ein zweiter wäre nur eine zweite Fehlerquelle. Drucken kann das Programm
nicht selbst, aber es kann dafür sorgen, dass der Ausweis in der Liste steht, aus der ohnehin
gedruckt wird.
