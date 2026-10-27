# 0072: Sonderausgaben (außerplanmäßige Ausgabe)

- Status: Angenommen
- Datum: 2026-10-27

## Problem

Manchmal gibt eine Ausgabestelle außer der Reihe aus, z. B. vor Weihnachten an einem Mittwoch
für die Kunden, die sonst donnerstags kommen, oder für einzelne Kundengruppen. bintafeln las bisher
überall nur die Wochentage der Kundengruppen. Am Einlass stand die Ampel dann für die richtigen
Kunden auf „heute nicht dran“, der Zähler oben rechts und der Aufruf passten nicht.

## Entscheidung

- Neues Modell `Sonderausgabe` (App `ausgabe`): Datum, Ausgabestelle, optional „Kunden vom
  Wochentag“, beliebig viele einzelne Kundengruppen (auch von anderen Ausgabestellen),
  Anmerkung. Je Tag und Ausgabestelle höchstens eine. Gepflegt unter „Einstellungen → Ausgabe →
  Sonderausgaben“ (Recht `einstellungen.listen`); ein Wochentag oder mindestens eine Gruppe ist
  Pflicht.
- **An einem Sondertag sind genau die gewählten Kunden dran**, die regulären des Tages nicht.
- Eine Stelle entscheidet, wer an einem Tag dran ist: `apps/ausgabe/ausgabetag.py`
  (`gruppen_am()`, `dran()`). Ampel, Fortschritt in der Kopfzeile, Aufruf (außer im Probelauf
  mit eingestelltem Wochentag) und der Start-Ausgabetag der Kundenliste fragen dort.
- Die Ampel meldet Nichtgewählte mit eigener, anpassbarer Meldung („nicht_dran_sonder“). Für
  ausdrücklich gewählte Gruppen anderer Ausgabestellen entfällt der Hinweis „andere
  Ausgabestelle“. Der Einlass zeigt oben „Heute Sonderausgabe“ mit der Auswahl.

## Begründung

Eine Stelle für die Frage „wer ist heute dran“ verhindert, dass Ampel, Zähler und Aufruf
auseinanderlaufen. Sonderausgaben sind Einstellungen der Tafel und gehören in die Sicherung
(Bereich Einstellungen).
