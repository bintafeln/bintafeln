# ADR 0133: Adressnummern

## Problem

Im Adressbuch haben nur Mitglieder eine Nummer (Mitgliedsnummer, ADR 0046); Spender, Märkte und
andere Adressen haben keine. Durch den Abruf aus dem Vereinsportal kommen viele Spender dazu. Aus
Vereinsprogrammen sind die Tafeln gewohnt, dass jede Adresse eine Nummer hat und man an ihr sieht,
wozu sie gehört: Mitglieder im unteren Bereich (1, 2, 3 …), alle anderen ab z. B. 2000.

## Entscheidung

- `Adresse.nummer` (**Adressnummer**) für alle Adressen ohne Mitgliedschaft. Mitglieder behalten
  ihre Mitgliedsnummer; sie gilt im Adressbuch als ihre Nummer (`Adresse.nummer_anzeige`).
- Vergeben wird automatisch beim Speichern (`Adresse.save()`) aus einem eigenen Zähler
  (`AdressEinstellungen.naechste_nummer`, Vorgabe **2000**), gesperrt gegen doppelte Vergabe.
  Übersprungen werden vergebene Adressnummern und gleich lautende Mitgliedsnummern, damit eine
  Nummer im Adressbuch immer nur eine Adresse meint.
- Wer als Mitglied angelegt wird (Adresse mit „Ist Vereinsmitglied“, Import von Mitgliedern),
  bekommt keine Adressnummer. Wird ein Spender später Mitglied, behält er seine Adressnummer; in der
  Liste gilt dann die Mitgliedsnummer, auf dem Adressblatt stehen beide.
- Die nächste Adressnummer steht unter „Einstellungen → Mitglieder“ neben der nächsten
  Mitgliedsnummer. Erreicht die nächste Mitgliedsnummer den Bereich der Adressnummern, warnt die
  Seite.
- Liste: Spalte „Nr.“ (sortierbar, mit Nullen aufgefüllt sortiert), Suche nach der Nummer.
- Beim Update vergibt die Migration `adressen/0015` allen vorhandenen Adressen ohne Mitgliedschaft
  eine Nummer in der Reihenfolge, in der sie angelegt wurden, und setzt den Zähler dahinter.

## Begründung

Getrennte Bereiche machen die Nummer aussagekräftig, ohne Mitgliedsnummern umzustellen, die die
Tafeln schon führen. Ein eigener Zähler hält beide Kreise unabhängig (wie Personalnummern,
ADR 0116); das Überspringen gleich lautender Mitgliedsnummern verhindert Verwechslungen, falls sich
die Bereiche doch einmal berühren.

## Folgen

- Das CSV-Format des Adressbuch-Imports/-Exports bleibt unverändert.
- Beim Zurückgehen auf eine ältere Version fallen die Adressnummern mit dem Feld wieder weg; ein
  späteres Update vergibt sie neu.
