# 0110: Besuche eines Tages aus tafelarbeit.de übernehmen (mit Kontostand)

- Status: Angenommen
- Datum: 2026-11-05
- Ergänzt: ADR 0100 (Bexat-Import), ADR 0014 (Kundenkonto), ADR 0006 (Importformat)

## Problem

Während eine Tafel von tafelarbeit.de (Bexat) auf bintafeln umzieht, läuft die **Ausgabe noch im
Altsystem**: Wer kommt, wird dort erfasst, und dort wird auch das **Kundenkonto** geführt (einige
zahlen den ganzen Monat im Voraus). bintafeln soll diese **Lücke** schließen können, damit Besuche
und Kontostände schon stimmen, bevor der eigentliche Umstieg erfolgt.

tafelarbeit.de kann eine **Tagesliste der Abholungen** als CSV oder Excel ausgeben (nur
Kundennummern, keine Namen) mit Kundennummer, Tag, Betrag und **Kontostand**.

## Entscheidung

- Das Bexat-Modul bekommt eine Seite **„Besuche & Konto nachtragen“**
  (`apps/bexat/besuche_konto.py`, `bexat:besuche_konto`). Sie liest die Tagesliste (CSV **oder**
  Excel, Spalten tolerant über die Überschriften) und:
  1. trägt je Kunde den **Besuch** als `Abholung` nach (Datum, Uhrzeit, Beitrag; je Kunde und Tag
     nur einmal – idempotent);
  2. setzt den **Kontostand** je Kunde genau auf den Wert aus der Liste – nicht direkt, sondern über
     eine **Korrektur-Buchung** (`apps.ausgabe.konto.korrigieren`, ADR 0014), mit Begründung
     „Abgleich tafelarbeit.de (Stand …)“. Die Differenz zum aktuellen Stand wird gebucht; passt der
     Stand schon, fällt die Buchung weg (Differenz 0).
- **Erst Probelauf, dann Übernehmen:** Ein Probelauf zeigt je Kunde den alten und neuen Kontostand,
  die zu buchende Differenz, die Zahl neuer Besuche und unbekannte Kundennummern. Erst „Übernehmen“
  bucht, in einer Transaktion.
- **Der exportierte Kontostand ist die Wahrheit.** Weil er Vorauszahlungen bereits enthält, stimmt
  das Konto nach der Korrektur automatisch – ohne dass einzelne Einzahlungen bekannt sein müssen.
  Bei mehreren Tagen in einer Datei zählt für den Kontostand der **jüngste** Tag je Kunde.
- **Rechte:** Die Seite erfordert `kunden.importieren`; das Buchen der Kontostände erfordert
  zusätzlich `konto.korrektur`. Ohne dieses Recht ist „Übernehmen“ gesperrt.
- **Keine Personendaten, keine festen Werte** im Code; die hochgeladene Datei wird nur gelesen,
  nicht gespeichert. Tests nutzen erfundene Daten.

## Begründung

- Der Kontostand als Wahrheit ist der einzige Weg, der die **Vorauszahler** ohne Kenntnis der
  einzelnen Zahlungen korrekt abbildet; die Korrektur-Buchung hält die Regel aus ADR 0014 ein
  (Konto nie direkt ändern) und ist nachvollziehbar.
- Probelauf + eigenes Recht schützen vor versehentlichen Geldbuchungen.
- Als Teil des Bexat-Moduls bleibt der Kern frei von altsystemspezifischem Code (ADR 0049, 0100);
  die neutrale Abholung/Buchung ist dieselbe wie beim normalen Import.

## Folgen

- Weil der Kontostand aus der Liste gesetzt wird, **überschreibt** eine Korrektur eventuelle in
  bintafeln selbst eingegebene Konto-Änderungen für dieselben Kunden. Für die Übergangszeit (Konto
  läuft noch in tafelarbeit.de) ist das gewollt; der Probelauf weist darauf hin. Nach dem Umstieg
  wird diese Seite nicht mehr verwendet.
- Unbekannte Kundennummern (nicht in bintafeln) werden übersprungen und gemeldet.
- Mehrfaches Einlesen desselben Tages ändert nichts doppelt (Besuch-Dedupe je Kunde+Tag, Korrektur
  nur bei Differenz).
