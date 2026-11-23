# ADR 0168: Nachricht der Fahrdienstleitung an die Mannschaft

## Problem

Unterwegs muss die Fahrdienstleitung die Mannschaft einer Tour manchmal sicher erreichen: „Bitte
im Büro anrufen“, „Das Lager schließt heute um 12 Uhr“. Bisher ging das nur über einen neuen Stopp
vom Büro (ADR 0159) oder per Telefon. Eine Nachricht, die im Programm untergeht, hilft nicht.

## Entscheidung

- Wer Touren plant (`touren.planen`), schickt unter „Touren heute“ eine **Nachricht** an die
  Mannschaft einer Tour von heute oder an **alle Touren von heute**. Je Tour entsteht eine
  `Tournachricht`.
- Die Mannschaft bekommt sie auf demselben Weg wie einen neuen Stopp vom Büro: Push aufs Handy
  (`apps.core.push`, wer es eingeschaltet hat) und der **rote Brief** über jeder Seite, bis jemand
  aus der Mannschaft „Gelesen“ tippt. Die Kopfzeile zeigt immer das Älteste, das noch offen ist –
  Stopp oder Nachricht.
- Die Fahrdienstleitung sieht je Nachricht, **wer wann bestätigt hat**, oder „noch nicht
  bestätigt“. Ist auf einer Tour niemand mit Konto eingetragen, sagt das Programm das gleich beim
  Schicken.
- **Fertige Texte** (`Kurztext`) pflegt die Tafel unter „Touren → Einrichten“; drei sind
  vorgegeben. Sie stehen beim Schicken zum Antippen bereit, freier Text geht immer.
- Nur für heute, höchstens 300 Zeichen, keine Antwort der Mannschaft außer „Gelesen“. Nach 30
  Tagen gelöscht; „Tourtag zurücksetzen“ nimmt die Nachrichten des Tages mit.
- Regeln nur in `apps/touren/nachrichten.py`.

## Begründung

Der rote Brief ist bei den Fahrern schon bekannt und lässt sich nicht wegdrücken; ein zweiter Weg
für Nachrichten wäre nur verwirrend. „Sicher gesehen“ kann das Programm nicht erzwingen – liegt das
Handy in der Ablage und Push ist aus, sieht niemand etwas. Deshalb ist die Anzeige „noch nicht
bestätigt“ der wichtige Teil: Sie sagt der Fahrdienstleitung, wann sie anrufen muss. Antworten der
Mannschaft sind bewusst nicht dabei; unterwegs ist Tippen unpraktisch, und für Rückfragen gibt es
das Telefon.
