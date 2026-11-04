# ADR 0103: Kundenstamm selbst geführt (Import sperren, Hinweise ausblenden)

## Problem

In der ersten Ausbaustufe ist der Kundenstamm ein Abbild aus dem Altsystem: Jeder Import ersetzt
oder ergänzt den Bestand, und in bintafeln geänderte Haushalte können von einem Import wieder
überschrieben werden. Darum zeigt die Oberfläche an mehreren Stellen Hinweise wie „Solange der
Kundenstamm aus dem Altsystem kommt, kann ein Import diese Änderung überschreiben".

Sobald eine Tafel die Daten übernimmt und nicht mehr importiert (die „Übernahme" aus dem
Fachkonzept), sind diese Hinweise falsch und störend, und ein versehentlicher Import würde die
selbst gepflegten Daten überschreiben.

## Entscheidung

Eine Einstellung `KundenEinstellungen.selbst_gefuehrt` (Vorgabe aus) markiert, dass bintafeln den
Kundenstamm selbst führt. Ist sie an:

- Die Import-Hinweise auf der Kundenübersicht, beim Anlegen/Bearbeiten/Ansehen und beim Löschen
  eines Haushalts verschwinden (gesteuert über den Kontextprozessor `kundenstamm_selbst_gefuehrt`).
- Der Kundenstamm-Import ist gesperrt: Der Import-Assistent bietet das Ziel „Kundenstamm" nicht
  mehr an, und die Ansichten `kunden:import_vorschau`/`kunden:import_uebernehmen` lehnen ab und
  leiten zur Übersicht zurück (greift auch für den Weg über den Bexat-Import, der denselben
  Abgleich benutzt).

Die Einstellung steht unter „Einstellungen → Kundenstamm" und lässt sich jederzeit wieder
abschalten, wenn doch noch einmal importiert werden soll.

## Begründung

- Eine einzige, umkehrbare Einstellung statt verstreuter Textlöschungen: Tafeln, die noch
  importieren, behalten die korrekten Warnungen; Tafeln, die übernommen haben, werden sie los.
- Die Sperre sitzt an der gemeinsamen Engstelle (`import_vorschau`/`import_uebernehmen`), über die
  alle Kundenstamm-Importe laufen – so kann kein Weg (Importformat, Import-Assistent, Bexat) die
  selbst geführten Daten versehentlich überschreiben.
- Kein fester Stichtag im Code; die Tafel entscheidet selbst, wann sie umschaltet (Fachkonzept).
