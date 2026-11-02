# 0102: Kundenstamm-Abgleich über einen Trigramm-Index

- Status: Angenommen
- Datum: 2026-11-02

## Problem

Der Abgleich eines Antrags mit dem Kundenstamm (Aufnahme-Assistent ADR 0028, Warteliste-Abgleich,
Dublettensuche) verglich jeden Antrag mit **jeder** Person im Stamm über eine Namensähnlichkeit in
Python. Bei einem großen Kundenstamm (z. B. nach einem Alt-Import) sind das Millionen Vergleiche je
Seitenaufruf. Der Vorgang dauerte dann länger als das Server-Zeitlimit (gunicorn), wurde abgebrochen
und die Seiten „Abgleich mit dem Kundenstamm“ und „Doppelte Anträge“ ließen sich nicht mehr öffnen.

## Entscheidung

- Die Datenbank macht die **Vorauswahl** über einen Trigramm-Index (PostgreSQL-Erweiterung
  `pg_trgm`). Jede Person bekommt einen normalisierten Suchnamen `Person.such_name`
  (`apps/kunden/namen.py`, dieselbe Normalisierung wie der genaue Vergleich), auf dem ein
  GIN-Index (`gin_trgm_ops`) liegt.
- `apps/antraege/aufnahme.py` holt mit `kandidaten(vorname, nachname)` nur noch die Personen mit
  **ähnlichem** Namen aus der Datenbank (beide Namensreihenfolgen, damit vertauschte Vor-/Nachnamen
  gefunden werden) und bewertet nur diese genau weiter. Die Bewertung selbst (Punkte, Gründe,
  Schwelle) bleibt unverändert – es werden dieselben Treffer gefunden, nur schneller.
- Die Dublettensuche (`apps/warteliste/ablauf.py`) normalisiert die Namen der offenen Anträge einmal
  vorab statt bei jedem Paarvergleich erneut.

## Begründung

- Der Trigramm-Index ist für genau diesen Zweck gedacht (unscharfe Namenssuche) und skaliert mit der
  Datenbank, statt den ganzen Stamm in Python zu durchlaufen.
- `such_name` wird aus Vor- und Nachname berechnet und nie von Hand gepflegt: gesetzt in
  `Person.save()` und – weil der Import `bulk_create` nutzt und `save()` dort nicht läuft – auch
  direkt beim Import (`importieren._person`). Eine Datenmigration füllt den Wert für vorhandene
  Personen und ist umkehrbar.
- Die Vorauswahl ist bewusst großzügig (Trigramm-Standardschwelle); die genaue Bewertung ab 50 %
  Namensähnlichkeit entscheidet weiterhin, was als Treffer zählt.

## Folgen

- `django.contrib.postgres` ist in `INSTALLED_APPS`; die Migration legt die Erweiterung `pg_trgm`,
  das Feld `such_name` und den GIN-Index an (umkehrbar).
- `apps/antraege/aufnahme.normal` liegt jetzt in `apps/kunden/namen.py` (von beiden Seiten genutzt,
  ohne Zirkelbezug) und bleibt als `aufnahme.normal` erreichbar.
- `such_name` ist von django-auditlog ausgenommen, weil es abgeleitet ist.
