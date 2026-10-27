# 0075: Krankmeldung eines Kunden

- Status: Angenommen
- Datum: 2026-10-27

## Problem

Kunden sind zeitweise krank, in Reha oder im Krankenhaus und kommen dann nicht. Die Ausgabestelle
soll das festhalten können, damit alle Bescheid wissen. Bisher ging das nur als freie Notiz ohne
Zeitraum; sie blieb stehen, bis jemand sie löschte, obwohl sie Gesundheitsdaten enthält.

## Entscheidung

- Zuschaltbar unter „Einstellungen → Kundenstamm“ (`KundenEinstellungen.krankmeldung`, Vorgabe
  aus).
- Eine Krankmeldung ist eine `Notiz` mit `krank_von`, `krank_bis` und grobem Grund
  (`KRANK_GRUENDE` in `apps/core/auswahl.py`: krank, Reha, Krankenhaus) und einer freiwilligen
  Anmerkung. Logik in `apps/kunden/krankmeldung.py`. Eintragen darf, wer Notizen schreiben darf
  (`kunden.notizen`), am Einlass und auf der Haushaltsseite.
- Der Einlass zeigt eine laufende Krankmeldung unter der Ampel. Die Ampel selbst ändert sich nicht.
- Nach dem Ende ist die Notiz nicht mehr zu sehen und wird beim täglichen Lauf gelöscht
  (`verwaiste_notizen_loeschen()`). Höchstens 365 Tage.
- Wer in der Zeit für den Kunden abholen darf, legt allein die Verwaltung beim Haushalt fest
  (Abholberechtigte). Die Krankmeldung gibt niemanden frei, weil sie auch die Ausgabestelle
  einträgt.

## Begründung

Als Notiz hängt die Krankmeldung an der Kundennummer, übersteht den Import und ist ohne Weiteres
in Auskunft, Papierkorb und Datensicherung enthalten. Ein grober Grund und das automatische
Löschen halten die Gesundheitsdaten so knapp und so kurz wie möglich.
