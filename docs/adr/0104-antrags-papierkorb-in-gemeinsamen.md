# ADR 0104: Antrags-Papierkorb in den gemeinsamen Papierkorb überführen

## Problem

Anträge (ADR 0024) hatten einen eigenen Papierkorb: Ein gelöschter Antrag wurde nicht entfernt,
sondern mit `Antrag.papierkorb_am` markiert und blieb in der Antragsliste unter einem eigenen
Reiter „Papierkorb" sichtbar, mit eigenen Fristen (`papierkorb_nach_tagen` fürs Wegräumen
abgeschlossener Anträge, `loeschen_nach_tagen` fürs endgültige Löschen).

Daneben gibt es seit ADR 0073 den gemeinsamen Papierkorb (`apps.core.papierkorb`), über den alle
anderen gelöschten Daten laufen (Haushalte, Adressen, Listen …). Es gab damit zwei „Papierkörbe" an
verschiedenen Stellen – verwirrend, und gelöschte Anträge tauchten nicht dort auf, wo man gelöschte
Daten sonst sucht.

## Entscheidung

Anträge nutzen denselben gemeinsamen Papierkorb wie alles andere.

- Löschen eines Antrags (`antraege:papierkorb`, Recht `antraege.loeschen`) legt ihn über
  `apps.antraege.models.in_papierkorb()` in den gemeinsamen Papierkorb – mit allem, was daran hängt
  (Personen, Nachweise samt verschlüsselten Dateien, Anmerkungen). Von dort wiederherstellbar.
- Das Feld `Antrag.papierkorb_am`, der eigene Reiter „Papierkorb" in der Antragsliste und das
  endgültige Löschen in der Antragsliste entfallen; das endgültige Löschen besorgt der gemeinsame
  Papierkorb.
- Eine automatische Frist bleibt (Datenschutz): `papierkorb_nach_tagen` legt abgeschlossene Anträge
  weiterhin nach N Tagen weg – jetzt in den gemeinsamen Papierkorb. Dort werden sie nach der
  Tafel-weiten Frist („Papierkorb leeren nach", `TafelEinstellungen.papierkorb_tage`) endgültig
  gelöscht. Die zweite, Antrags-eigene Frist `loeschen_nach_tagen` entfällt.
- Eine Datenmigration überführt bereits gelöschte Anträge (mit gesetztem `papierkorb_am`) einmalig
  in den gemeinsamen Papierkorb; nichts wird dabei gelöscht.

## Begründung

- Ein einziger Papierkorb, in dem man filtern kann (ADR 0073), statt mehrerer Stellen – das war der
  ausdrückliche Wunsch.
- Gelöschte Anträge werden wie alle anderen Daten behandelt: gleiches Wiederherstellen, gleiches
  Änderungsprotokoll (anders als früher wird das Protokoll eines gelöschten Antrags nicht mehr
  getilgt – es bleibt erhalten wie bei Haushalten), gleiche endgültige Löschung mit den Dateien.
- Die automatische Löschung bleibt erhalten (Grundsatz „Löschfristen je Datenart mit automatischer
  Löschung"): abgeschlossene Anträge werden weiter von selbst weggeräumt; nur die doppelte
  Fristen-Verwaltung entfällt zugunsten der einen Tafel-weiten Papierkorb-Frist.
- Das sofortige, endgültige Löschen eines Antrags (ohne Papierkorb) gibt es nur noch beim
  Zurücksetzen der Demo-Daten (`apps.antraege.models.loeschen`).
