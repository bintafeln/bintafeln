# ADR 0108: Anträge im Stapel aus einer CSV importieren

## Problem

Tafeln, die von einem Altsystem (einem anderen Tafelprogramm) zu bintafeln wechseln, haben oft viele
hundert offene Anträge mit allen Feldern (Name, Adresse, Haushalt, Nachricht) und Nachweisen.
Bisher konnte bintafeln nur die **Nachweise** im Stapel übernehmen (ADR 0024, ZIP +
`nachweise.csv`), die Anträge selbst nur einzeln über das öffentliche Formular. Das Modul „Übernahme aus einem anderen Programm“
(ADR 0100) erzeugte zwar eine `antraege.csv`, es gab aber keine Stelle, die sie einliest.

## Entscheidung

Ein **Antrags-Import** in der Antragsliste (Recht `antraege.bearbeiten`) liest eine `antraege.csv`
und legt daraus Anträge an. Logik in `apps/antraege/antrag_import.py` (`pruefen()`/`uebernehmen()`,
wie beim Nachweis-Import), Ansicht `antraege_importieren`.

- **Format = Export der Antragsliste:** gleiche Spalten, Trennzeichen `;`, UTF-8. Pflicht sind nur
  `vorname` und `nachname`; alles andere ist optional. Weitere Haushaltspersonen stehen in der
  Spalte `personen` (`` | ``-getrennt, je Person „Vorname Nachname JJJJ-MM-TT (Staat)“); eine
  optionale `anmerkung` wird als interne Anmerkung angelegt.
- **Antragsnummer:** Ist `nummer` angegeben und schon vorhanden (oder zweimal in der Datei), wird
  die Zeile übersprungen – kein Doppelimport, auch bei stapelweisen Läufen. Ohne `nummer` vergibt
  bintafeln die nächste Nummer. So bleibt die ursprüngliche Antragsnummer erhalten, über die danach
  die **Nachweise** (ADR 0024) zugeordnet werden. Sinnvolle Reihenfolge: erst Anträge, dann
  Nachweise.
- **Probelauf** (Vorgabe): zeigt nur einen Bericht mit Zählern je Status (`ok`, `dublette`,
  `unvollstaendig`, `fehler`) – ohne Namen, nur Zeilennummer und Antragsnummer. Zum Übernehmen den
  Haken entfernen. Eine fehlerhafte Zeile stoppt die anderen nicht.

bintafeln kennt nur dieses neutrale Format. Das Werkzeug, das die Daten aus einem bestimmten
Altsystem herunterlädt und die Datei(en) erzeugt, gehört nicht in dieses Repository (siehe
CLAUDE.md).

## Begründung

Das Export-Format wiederzuverwenden heißt: ein Format weniger, Export und Import passen zusammen
(eine Tafel kann ihre Anträge sichern und wieder einspielen), und ein externes Übernahme-Werkzeug
muss nur die bekannten Export-Spalten erzeugen. Die Nachweise bleiben beim bestehenden, getrennten
ZIP-Import – so bleibt jeder Schritt einfach und wiederholbar, und große Mengen lassen sich in
Stapeln übernehmen.
