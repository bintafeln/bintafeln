# 0035: Rücknahmen am Einlass nur über Korrekturwünsche

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Bisher konnte der Einlass eine Abholung, Zahlung oder Sonderaktion am selben Tag selbst
zurücknehmen. Das soll nicht mehr möglich sein: Änderungen an Kunden und an der Kasse entscheiden
Admins oder eine dafür berechtigte Rolle.

## Entscheidung

- Neues Recht `einlass.zuruecknehmen` (Vorgabe: nur Admin): direkt zurücknehmen, auch an
  späteren Tagen.
- Ohne dieses Recht gibt es am Einlass „Korrektur beantragen“ mit Grund aus einer festen Liste
  (`KORREKTURGRUENDE`) und optionaler Anmerkung. Es entsteht ein `Korrekturwunsch` an der
  Kundennummer; je Eintrag höchstens ein offener.
- Recht `korrekturen.entscheiden` (Vorgabe: nur Admin): Seite „Korrekturwünsche“, Zurücknehmen
  oder Ablehnen mit Antwort. Benachrichtigung per Mail an alle Berechtigten, Zahl auf der
  Startseite.
- Die Rücknahme selbst läuft für alle Wege über `apps/ausgabe/korrekturen.zuruecknehmen()`, die
  Kundenkonto, letzten Besuch und Kasse mitkorrigiert.
- Entschiedene Wünsche gelten wie Abholungen und werden nach deren Frist gelöscht.

## Begründung

Ein Wunsch mit Grund schafft Nachvollziehbarkeit, ohne den Einlass aufzuhalten. Die Empfänger
ergeben sich aus den Rechten, so kann jede Tafel festlegen, wer entscheidet.
