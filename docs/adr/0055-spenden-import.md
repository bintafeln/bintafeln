# 0055: Spenden-Import aus CSV

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Viele Spenden stehen schon in einem Vereinsportal oder auf Kontoauszügen. Das bisherige
Zusatzprogramm meldete sich dafür per Fernsteuerung im Portal an (mit gespeicherten
Zugangsdaten) und las Namen und Beträge aus den PDF-Belegen. Das bricht bei jeder Änderung des
Portals und braucht Zugangsdaten, die bintafeln nicht speichern soll.

## Entscheidung

- bintafeln liest ein neutrales CSV-Format (`apps/spenden/importieren.py`): Spalten der Spende
  (datum, betrag, art, beschreibung, zahlungsweg, zweck, belegnummer, mitgliedsbeitrag) und des
  Spenders (organisation, anrede, vorname, nachname, strasse, plz, ort, email, Einwilligungen).
  Den Export des Portals bringt man einmal mit Excel in dieses Format.
- Zwei Schritte wie bei Adressen und Kundenstamm: Prüfbericht, dann Übernehmen in einer
  Transaktion. Bis dahin liegt die Datei verschlüsselt in der Sitzung.
- Spender über die E-Mail oder Name+PLZ zuordnen; sonst neue Adresse. Vorhandene Adressen werden
  nie geändert.
- Neues Feld `Spende.belegnummer` (eindeutig, wenn gesetzt): Eine Spende mit bekannter
  Belegnummer wird übersprungen, der Import ist also wiederholbar.
- Recht „Spenden erfassen“; kein Zugriff auf fremde Systeme.

## Begründung

Ein offenes Format funktioniert mit jedem Portal und jeder Bank, ohne Zugangsdaten und ohne
Abhängigkeit von fremden Oberflächen. Die Belegnummer macht wiederholtes Einlesen ungefährlich.
