# ADR 0184: Stationen und Adressbuch gleichen sich ab

## Problem

Stationen der Touren ließen sich einmalig ins Adressbuch übertragen (ADR 0147); danach liefen
beide getrennt. Zog ein Markt um oder änderte sich die Telefonnummer, musste das an zwei Stellen
gepflegt werden – und wurde es oft nur an einer. Als Kategorie bekam die Adresse die Art der
Station („Markt“, „Bäckerei“ …), sodass neben der im Büro üblichen Kategorie „Märkte und
Lieferanten“ weitere entstanden und ein Serienbrief nicht alle erreichte.

## Entscheidung

- **Kategorie aus den Einstellungen.** Märkte, Bäckereien und Lieferanten bekommen eine
  gemeinsame Kategorie, Einrichtungen eine zweite. Die Namen stehen in `TourenEinstellungen`
  (Vorgabe „Märkte und Lieferanten“ und „Soziale Einrichtung“, leer = keine). Es wird nur
  hinzugefügt, nie weggenommen; schon Übertragene bekommen sie beim nächsten Speichern der Station
  oder mit dem Knopf „Alle … übertragen“.
- **Abgleich in beide Richtungen** für Name, Ansprechperson, Straße mit Hausnummer, PLZ, Ort,
  Telefon und E-Mail. Übernommen wird nur die Angabe, die sich beim Speichern geändert hat
  (Vergleich mit dem Stand in der Datenbank vor dem Speichern).
- **Beim Verknüpfen** mit einer vorhandenen Adresse wird ergänzt, was auf einer Seite leer ist;
  wo beide etwas anderes haben, bleibt beides stehen.
- Angeschlossen über `pre_save`/`post_save` im Modul Touren (`apps.py`), nicht im Kern.
  Ein leerer Name wird nie übernommen.
- **Ausgabestellen der Tafel** (ADR 0171) hängen mit drin: Speichern der Ausgabestelle zieht die
  Station sofort nach (nicht erst im täglichen Lauf) und über sie das Adressbuch; eine Änderung im
  Adressbuch geht an die Ausgabestelle, die Station folgt. An der Station bleiben diese Angaben
  gesperrt. Ein Name, den schon eine andere Ausgabestelle trägt, wird nicht übernommen.

## Begründung

- Eine Angabe, die an zwei Stellen steht, wird nur gepflegt, wenn eine Änderung genügt. Wer die
  Änderung erfährt – Fahrdienstleitung oder Büro –, soll sie dort eintragen können, wo er arbeitet.
- „Nur das Geänderte“ verhindert, dass bestehende Unterschiede (z. B. aus früheren Übertragungen)
  beim Speichern einer ganz anderen Angabe ungefragt überschrieben werden.
- Die Namen der Kategorien gehören der Tafel, deshalb stehen sie in den Einstellungen und nicht
  im Code.
- Signale statt Aufrufen im Kern: Das Adressbuch weiß nichts von Stationen (ADR 0049).
