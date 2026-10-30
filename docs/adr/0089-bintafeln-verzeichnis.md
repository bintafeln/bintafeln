# 0089 – Freiwillige Meldung im bintafeln-Verzeichnis

## Problem

Der Herausgeber weiß nicht, welche Tafeln bintafeln einsetzen und mit welcher Version. Bei
einer Sicherheitslücke kann er sie nicht gezielt warnen. GitHub zeigt nur anonyme Zahlen, und
ein Programm, das heimlich „nach Hause telefoniert“, passt nicht zum Datenschutz.

## Entscheidung

- Unter „Einstellungen → Tafel → bintafeln-Verzeichnis“ kann eine Tafel sich **freiwillig**
  melden (Vorgabe: aus). Gemeldet werden nur Name der Tafel, eine Kontakt-Mail (leer = E-Mail der
  Tafel), die Version und eine zufällige Kennung der Installation – nie Kunden- oder
  Personendaten. Die Seite zeigt genau diese Angaben und die Zieladresse.
- Gemeldet wird beim Einschalten, nach jedem Update und sonst einmal pro Woche
  (`manage.py verzeichnis_melden`, im Takt der Benachrichtigungen in `docker/entrypoint.sh`).
  Ausschalten löscht den Eintrag beim Empfänger. Die Demo meldet nie.
- Ziel ist `BINTAFELN_VERZEICHNIS_URL`, leer = Adresse des Herausgebers aus `bintafeln/programm.py`.
- Der Empfang steckt im selben Programm: Mit `BINTAFELN_VERZEICHNIS_EMPFANG=true` nimmt eine
  Installation (die des Herausgebers) Meldungen unter `/verzeichnis/melden/` an (JSON, höchstens
  4 KB, 30 je Adresse und Stunde, höchstens 5000 Einträge) und zeigt sie unter „Gemeldete
  Tafeln“ (Recht `einstellungen.tafel`). Wer zwei Wochen nichts gemeldet hat, ist markiert.
- Logik in `apps/core/verzeichnis.py`, Ansichten in `apps/core/views_verzeichnis.py`.

## Begründung

Freiwillig und offen gelegt, was gemeldet wird, bleibt das Vertrauen der Tafeln erhalten. Die
wöchentliche Meldung zeigt, welche Installationen noch laufen und welche Versionen im Einsatz
sind. Ein Empfang im selben Programm braucht keinen zusätzlichen Dienst.
