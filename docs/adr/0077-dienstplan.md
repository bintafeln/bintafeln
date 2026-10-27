# 0077: Dienstplan der Ausgabe

- Status: Angenommen
- Datum: 2026-10-27

## Problem

Die Helferinnen und Helfer einer Ausgabe werden über einen gedruckten Plan je Wochentag
eingeteilt (Teamleitung, Frühdienst, Vorsortierung, Kasse, Brot, Mopro, Wurst/Fleisch,
Sonderartikel, Obst, Gemüse, Springer – Spalten für die Termine des Monats). Wer nicht kann,
meldet sich telefonisch bei der Teamleitung des Tages ab; jeden Monat wird der Plan neu
geschrieben, obwohl er sich jede Woche wiederholt. Ausgabestellen und Ausgabetage sind je Tafel
verschieden, und viele Helfer haben kein Konto in bintafeln.

## Entscheidung

- Neues zuschaltbares Modul `dienstplan` (ADR 0049), gebaut wie der Fahrdienst (ADR 0074).
  Modelle: `DienstStelle` (je Ausgabestelle einzeln einschaltbar, eigene Ausgabetage),
  `Diensttag` (Teamleitung und Telefon für Abmeldungen je Wochentag), `Aufgabe` (Name, Zeit,
  Reihenfolge, Pflicht; eine Zeile im Plan), `Besetzung` (feste Besetzung je Aufgabe),
  `Helfer`, `Ausfall`, `Ersatz`, `DienstplanEinstellungen`.
- `Helfer` mit oder ohne Konto: Mit Konto sieht die Person den Plan und meldet ihren Ausfall
  selbst (wenn die Tafel das einstellt), ohne Konto genügen Name und Telefon.
- Der Plan eines Tages entsteht aus der festen Besetzung, nichts wird je Monat gespeichert
  (Regeln in `apps/dienstplan/plan.py`). Als Ersatz stehen nur Helfer zur Wahl, die an dem Tag
  weder ausfallen noch schon eingeteilt sind; zusätzlich ein Gast als Freitext.
- Jeder Ausfall geht per E-Mail an die Teamleitung der betroffenen Ausgabetage, sonst an alle mit
  „Dienstplan planen“; optional Telegram ohne Grund und Anmerkung. Der Telegram-Versand liegt
  jetzt für Fahrdienst und Dienstplan gemeinsam in `apps/core/telegram.py`.
- PDF je Monat und Ausgabestelle, A4 quer wie der Papierplan: je Ausgabetag eine Seite, gelb nur
  hinter „offen“ und „unbesetzt“, unten „Abmeldungen bitte bei … unter …“.
- Beispiel-Dienstplan (`apps/dienstplan/beispiel.py`, Knopf und Befehl `dienstplan_beispiel`)
  mit erfundenen Helfern ohne Konto; Entfernen löscht nur diese.
- Rechte `dienstplan.sehen` (Büro, Ausgabe) und `dienstplan.planen` (Büro).

## Begründung

Der Aufbau des Fahrdienstes hat sich bewährt; dieselben Begriffe (Ausfall, Ersatz, offen) machen
beide Module leicht verständlich. Helfer ohne Konto sind nötig, weil viele Ehrenamtliche nur
gelegentlich kommen und kein Konto brauchen. Die Teamleitung je Ausgabetag ist die Person, die
auf Papier die Abmeldungen annimmt, deshalb bekommt sie die Nachricht.
