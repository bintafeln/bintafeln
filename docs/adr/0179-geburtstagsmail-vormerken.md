# ADR 0179: Glückwunsch zum Geburtstag vormerken – der Server schickt am Tag

## Problem

Die Glückwunsch-Mail (ADR 0178) lässt sich nur am Geburtstag und in den Tagen danach schicken.
Wer weiß, dass er jemandem auf jeden Fall gratulieren will, möchte das vorbereiten können, wenn er
gerade Zeit hat – auch wenn er am Tag selbst nicht im Programm ist.

## Entscheidung

- **Vormerken statt Senden:** Liegt der Geburtstag in der Zukunft (höchstens ein Jahr), öffnet
  derselbe Weg dieselbe Seite mit der fertigen Mail. Der Knopf heißt „Am Geburtstag senden“, dazu
  kommt die **Uhrzeit je Mail** (Vorschlag: die zuletzt vom Konto gewählte, sonst 8 Uhr).
  Gespeichert wird `GeburtstagVormerkung` mit genau diesem Betreff und Text – eine spätere Änderung
  der Vorlage ändert die vorgemerkte Mail nicht mehr.
- **Wo:** im Geburtstagskalender gut sichtbar bei den nächsten 14 Tagen („Glückwunsch
  vorbereiten“), im Jahreskalender als kleiner Link bei jedem künftigen Geburtstag.
- **Bis zum Versand änderbar und löschbar** (Papierkorb). Alle, die schreiben dürfen, sehen
  „vorgemerkt für … von …“; je Person und Geburtstag gibt es eine Vormerkung.
- **Versand durch den Server:** `geburtstagsmail.faellige_senden()` läuft mit den gesammelten
  Benachrichtigungen alle fünf Minuten (`benachrichtigungen_senden`). Vor dem Senden wird geprüft,
  ob die Person noch zu den Mitarbeitenden gehört und eine E-Mail-Adresse hat. Danach gilt alles
  wie beim Senden von Hand (Mail-Archiv, Versand, `GeburtstagMail`, „Gratuliert“ für das Konto);
  die Vormerkung wird gelöscht.
- **Meldung an die Person, die vorgemerkt hat** (Benachrichtigung `geburtstagsmail`, ADR 0086):
  nach dem Versand – oder am Tag danach einmal, wenn es nicht ging. Scheitert der Versand, wird er
  am selben Tag bei jedem Lauf wieder versucht; danach bleibt die Vormerkung 30 Tage stehen und
  lässt sich von Hand nachträglich schicken (der vorbereitete Text steht dann schon da).
- Rechte wie in ADR 0178; keine neue Einstellung.

## Begründung

Die Schleife im App-Container gibt es schon; ein eigener Dienst oder Zeitplaner wäre für eine
Mail am Tag zu viel. Die Uhrzeit je Mail macht eine Einstellung für die ganze Tafel überflüssig.
Der feste Text schützt vor Überraschungen: Hinaus geht, was jemand gelesen hat.
