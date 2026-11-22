# ADR 0160: Touren – Fahrzeugart, Erstzulassung und Papiere zum Fahrzeug

Ergänzt ADR 0151 (Fahrzeuge und Fahrtenbuch).

## Problem

Zu den Fahrzeugen standen nur Name, Kennzeichen und Kilometerstand. Die Fahrdienstleitung will
auch wissen, was für ein Fahrzeug es ist und wie alt, und sie braucht Fahrzeugschein und
Fahrzeugbrief griffbereit – nicht im Ordner im Büro.

## Entscheidung

- **Fahrzeugart** (`Fahrzeug.typ`) als freier Text mit Vorschlägen aus den schon eingetragenen
  Arten. Keine feste Liste: Jede Tafel hat andere Fahrzeuge.
- **Erstzulassung** (`Fahrzeug.erstzulassung`) als Datum.
- **Papiere** als `FahrzeugDokument` je Fahrzeug: Fahrzeugschein, Fahrzeugbrief oder Sonstiges mit
  eigener Bezeichnung; Foto oder PDF bis 10 MB, verschlüsselt über `apps.core.privatdateien`.
  Mehrere je Art sind möglich (z. B. nach einer Ummeldung).
- **Wer darf:** sehen mit `touren.planen` oder `touren.fahrten` (Fahrdienstleitung), hinterlegen
  und entfernen nur mit `touren.planen`. Die Fahrer sehen die Papiere nicht. Entferntes kommt in
  den Papierkorb.
- Eine eigene Seite je Fahrzeug, erreichbar aus „Touren → Einrichten“.

## Begründung

- „Auswahl statt Freitext“ gilt, wo es feste Werte gibt; Fahrzeugmodelle sind je Tafel
  verschieden. Die Vorschläge halten die Schreibweise trotzdem einheitlich.
- Der Fahrzeugbrief ist ein Eigentumsnachweis und gehört nicht in jede Hand; deshalb verschlüsselt
  und nur für die Fahrdienstleitung.
- Kein neues Recht nötig: Wer Fahrzeuge einrichtet, pflegt auch ihre Papiere.
