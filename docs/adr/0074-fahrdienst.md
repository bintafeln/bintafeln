# 0074: Fahrdienst (Fahrerplan, Ausfälle, Ersatz)

- Status: Angenommen
- Datum: 2026-10-27

## Problem

Der Fahrdienst lief über einen gedruckten Monatsplan (Tage × Touren, je Tour Fahrer und
Beifahrer, darunter Springer). Wer nicht konnte, klebte einen gelben Zettel über seinen Namen;
die Fahrdienstleitung musste das sehen und von Hand Ersatz suchen. Niemand wurde benachrichtigt,
und jeden Monat wurde der Plan neu abgetippt, obwohl er sich jede Woche wiederholt.

## Entscheidung

- Neues zuschaltbares Modul `fahrdienst` (ADR 0049). Modelle: `Tour` (Plätze, Platz 1 = Fahrer),
  `Besetzung` (feste Besetzung je Wochentag und Platz), `Springer` (auf jeder Tour einsetzbar,
  optional nur an bestimmten Tagen), `Ausfall` (Zeitraum, Grund), `Ersatz` (Tag, Tour, Platz),
  `FahrdienstEinstellungen`.
- Der Plan eines Tages entsteht aus der festen Besetzung; nichts wird je Monat gespeichert.
  Regeln in `apps/fahrdienst/plan.py`: Ein Platz ist „offen“, wenn die Person, die ihn an dem Tag
  hat (Ersatz vor fester Besetzung), ausfällt. Fahrtage und Feiertage aus den Einstellungen.
- Zur Wahl als Ersatz stehen die an dem Tag freien Springer, danach weitere freie Fahrer und
  Beifahrer; wer ausfällt oder schon eingeteilt ist, nicht.
- Ob Fahrer und Beifahrer ihren Ausfall selbst melden, stellt die Tafel ein. Jeder Ausfall
  schickt eine E-Mail an die eingestellten Personen (normalerweise eine), sonst an alle mit
  „Fahrdienst planen“, mit betroffenen Einsätzen und freien Springern. Zusätzlich optional
  Telegram (`apps/fahrdienst/telegram.py`, Bot-Schlüssel über `apps.core.geheimnis`): ohne Grund
  und Anmerkung, weil die Nachricht über Server von Telegram läuft. WhatsApp nicht: Es gibt dafür
  nur die kostenpflichtige WhatsApp-Business-Plattform mit Firmenkonto bei Meta und vorab
  genehmigten Vorlagen – zu viel Aufwand für eine Tafel.
- Der Plan eines Monats als PDF (A3 quer, `apps/fahrdienst/pdf.py`).
- `Tour.mindestbesetzung`: Plätze darüber sind für Gäste ohne Konto (`Ersatz.gast` statt
  Benutzer, Freitext, weil es keine registrierte Person gibt). Ein leerer Pflichtplatz ist
  „unbesetzt“ und zählt wie ein offener.
- Beispiel-Fahrerplan (`apps/fahrdienst/beispiel.py`, Knopf und Befehl `fahrdienst_beispiel`):
  erfundene Konten mit Präfix `beispiel-fd-` ohne Passwort. Sie werden beim Entfernen wirklich
  gelöscht – die einzige Ausnahme von „Mitarbeitende nie löschen“ (ADR 0015), weil es nie echte
  Personen sind.
- Rechte `fahrdienst.sehen` (Fahrer, Beifahrer, Büro) und `fahrdienst.planen` (Büro). Den Grund
  eines Ausfalls (z. B. „krank“) sehen nur, wer plant, und die Person selbst.
- Ausfälle und Ersatz werden nach `aufbewahren_monate` (Vorgabe 12) gelöscht; sie stehen in der
  Auskunft für Mitarbeitende (neuer Hook `Modul.auskunft_mitarbeiter`). Löschen über den
  Papierkorb (ADR 0073).

## Begründung

Die feste Besetzung bildet den Wochenrhythmus ab, Ausfall und Ersatz sind Ausnahmen für einzelne
Tage – wie Aufkleber auf dem Papierplan, aber mit Benachrichtigung. „Krank“ ist eine
Gesundheitsangabe; deshalb sieht den Grund nur, wer planen muss, und die Daten sind befristet.
