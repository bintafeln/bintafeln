# ADR 0139: Ein Status je Antrag

## Problem

Mit eingeschalteter Warteliste hatte die Antragsseite zwei Status: oben den Antragsstatus (neu,
in Bearbeitung, erledigt, abgelehnt) und weiter unten im Abschnitt „Warteliste“ den Status der
Warteliste (wartend, eingeladen, erschienen, aufgenommen, gestrichen …), jeweils mit eigener
Auswahl und eigenem Knopf „Status speichern“. Beides hing ohnehin zusammen (aufgenommen ↔
erledigt, gestrichen ↔ abgelehnt) und war für das Büro verwirrend.

## Entscheidung

- Neuer Modul-Haken `Modul.antrag_status(request, antrag) -> HTML | ""`, aggregiert über
  `apps.core.module.antrag_status()`. Liefert ein Modul etwas, ersetzt es oben auf der Antragsseite
  die Auswahl des Antragsstatus.
- Die Warteliste liefert dort ihren Status, sobald der Antrag einen Wartestand hat; der Kasten
  „Status setzen“ im Abschnitt „Warteliste“ entfällt. Der Antragsstatus folgt wie bisher aus dem
  Warteliste-Status (`ablauf.streichen()` lehnt ab, die Aufnahme erledigt) und wird nicht mehr von
  Hand daneben gesetzt.
- Ohne Warteliste (oder ohne Wartestand) bleibt der einfache Antragsstatus.
- Darstellung: farbiges Kärtchen mit dem aktuellen Status, daneben eine normal große Auswahl, die
  sofort speichert (`data-sofort`); „Wartezeit“ zeigt dazu das Datumsfeld und speichert erst mit
  Datum (`sofort.js` sendet nur gültige Formulare).

## Begründung

Ein Status an einer Stelle ist eindeutig. Über den Modul-Haken bleibt Warteliste-Code aus dem Kern
(ADR 0049); ohne Modul ändert sich für eine Tafel nichts außer dem Aussehen.
