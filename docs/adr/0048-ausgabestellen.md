# 0048: Ausgabestellen mit Anschrift, Zeiten, Ansprechpartnern und Karte

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Eine Ausgabestelle war bisher nur ein Name. Mitarbeitende brauchen aber Anschrift, Zeiten,
Telefon, Ansprechpartner und Hinweise (Zugang, Schlüssel) an einer Stelle, und neue Helfer
wollen sehen, wo die Ausgabestelle liegt.

## Entscheidung

- `Ausgabestelle` bekommt Anschrift, Telefon, E-Mail und „Allgemeine Anmerkungen“.
- `AusgabestelleZeit`: Wochentag, von, bis, Art (Auswahl `ZEITARTEN`) und kurzer Hinweis.
- `AusgabestelleKontakt`: Zuständigkeit (Auswahl `ZUSTAENDIGKEITEN`), registrierte
  Mitarbeitende per Auswahl oder ein externer Name, Telefon, E-Mail. Kontakte mit Konto stehen
  in der Auskunft der Mitarbeitenden.
- Eigene Seiten unter „Kunden → Ausgabestellen“ (Recht `kunden.liste`): Übersicht und
  Detailseite mit Kundengruppen. Pflegen mit `einstellungen.listen`; die alte Listenpflege
  leitet dorthin um.
- Karte: Link „In Google Maps öffnen“ und eine eingebettete Karte, die erst nach Klick lädt
  (`static/js/karte.js`). Ohne Klick gehen keine Daten an Google; kein API-Schlüssel nötig.

## Begründung

Alle Angaben zu einer Ausgabestelle an einem Ort ersparen Zettel und Telefonlisten. Die
Zwei-Klick-Lösung für die Karte hält die Datensparsamkeit ein, ohne auf die Karte zu verzichten.
