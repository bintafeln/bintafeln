# 0071: Merkmale am Einlass und auf dem Ausweis

- Status: Angenommen
- Datum: 2026-10-27

## Problem

Einige Angaben zu den Kunden braucht der Einlass, z. B. ob jemand schwerbehindert ist, Hilfe beim
Einkauf braucht oder nichts hört. Im bisherigen Programm war „schwerbehindert“ ein Ja/Nein-Feld.
Bei „ja“ kam das Rollstuhl-Symbol auf den Ausweis. In bintafeln gab es dafür nur frei angelegte
Zusatzfelder. Der Einlass sah sie nicht, und auf den Ausweis kamen sie nicht.

## Entscheidung

- **Mitgelieferte Merkmale:** Eine Migration legt sechs Zusatzfelder „Ja/Nein, gilt für Person“
  an (`FESTE_MERKMALE` in `apps/core/auswahl.py`): Schwerbehindert, Vegetarier, Braucht Hilfe beim
  Einkauf, Taub, Stumm, Blind. Sie sind als `fest` markiert, lassen sich ab- und zuschalten
  (Aktiv), umbenennen und einstellen, aber nicht löschen. Art und Schlüssel bleiben fest. Gibt es
  schon ein Feld mit dem Schlüssel (z. B. aus dem Import), wird es übernommen, nicht verdoppelt.
  Eigene Merkmale legt die Tafel wie bisher als Zusatzfeld an.
- **Standard ist „nein“:** Ja/Nein-Felder sind beim Bearbeiten ein Ankreuzkästchen. Angekreuzt
  heißt ja, leer heißt nein. Ein leerer Wert gilt überall als nein.
- **Am Einlass** (Schalter `einlass` je Feld): Die Kundendaten zeigen unter „Merkmale“ je Person,
  was auf „ja“ steht. „Nein“ wird nicht gezeigt. Logik in `apps/kunden/merkmale.py`.
- **Auf dem Ausweis** (Feld `ausweis`: Rollstuhl-Symbol oder Kürzel): Das neue Element
  „Merkmale“ der Ausweis-Vorlage druckt je zutreffendem Merkmal ein Quadrat in der Farbe des
  Elements. Steht kein Merkmal auf „ja“, bleibt der Platz leer. Voreingestellt ist das
  Rollstuhl-Symbol bei „Schwerbehindert“. Gedruckt wird erst, wenn die Tafel das Element in ihre
  Vorlage setzt.

## Datenschutz

Schwerbehindert, Taub, Stumm und Blind sind Gesundheitsangaben (Art. 9 DSGVO) und deshalb als
besondere Kategorie markiert:

- Der Einlass sieht sie nur mit dem Recht „Angaben der besonderen Kategorie sehen“. Die Rolle
  Ausgabe hat es in der Vorgabe nicht.
- Sieht der Einlass eine solche Angabe, steht das im Zugriffsprotokoll.
- Ein Symbol auf dem Ausweis sieht jeder, der den Ausweis sieht. Die Einstellung sagt das, und
  die Tafel entscheidet selbst, ob sie das Element verwendet.

## Begründung

- Feste Schlüssel machen Import, Einlass und Ausweis ohne Einrichtung nutzbar.
- Dass die Merkmale normale Zusatzfelder bleiben, nutzt alles Vorhandene: Import
  (`zusatz_schwerbehindert`), Listen, Auskunft, Verlängerungsregeln, Vorrang im Aufruf.

## Nachtrag: Grad der Behinderung im Kundenstamm

„Neuer Haushalt“ und „Person bearbeiten“ zeigen Schwerbehindert, Taub, Stumm und Blind nicht mehr
als einzelne Häkchen. Wie im Antrag (ADR 0024) wird der Grad der Behinderung gewählt, mit GdB die
Merkzeichen; daraus folgen „Schwerbehindert“ (ab GdB 50) und „Blind“ (Bl, TBl). Das gilt auch für
jede angehörige Person. Taub und Stumm bleiben Merkmale für den Einlass, gespeicherte Werte bleiben
erhalten.
