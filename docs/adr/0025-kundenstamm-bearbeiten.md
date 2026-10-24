# 0025: Der Admin kann den Kundenstamm bearbeiten

- Status: Angenommen
- Datum: 2026-10-24
- Ändert: ADR 0006 (Kundenstamm nur lesend)

## Problem

Der Kundenstamm war bis zum Umstieg ein reiner Snapshot aus dem Altsystem. Kleine Korrekturen
(Anschrift, Sperre, neue Person, falsche Abholung) mussten bis zum nächsten Import warten. Die
Tafel möchte, dass der Admin alles ändern kann.

## Entscheidung

- Der **Admin** kann Haushalte anlegen, bearbeiten und löschen, ebenso Personen,
  Abholberechtigte, Sperren, Ausnahmen, interne Anmerkungen, Zusatzfelder und Abholungen
  (Löschen), dazu die Listen Kundengruppen, Ausgabestellen und Einkommensarten. Büro und
  Ausgabe bleiben beim Lesen bzw. beim Einlass.
- Feste Werte und Mitarbeitende sind Auswahlfelder; abgeschaltete Angaben (Datensparsamkeit)
  erscheinen auch beim Bearbeiten nicht. Werte inaktiver Zusatzfelder bleiben unberührt.
- Der **Kontostand** ändert sich weiter nur über Buchungen (ADR 0014). Wird eine Abholung
  gelöscht, wird ihre Buchung zurückgenommen. Gelöschte Haushalte hinterlassen ihre Buchungen
  ohne Haushalt, damit die Kasse vollständig bleibt.
- Der **Import bleibt ein Vollaustausch**: Er ersetzt auch alle Änderungen aus bintafeln. Jeder
  Haushalt merkt sich, wann und von wem er geändert wurde; die Bearbeitungsseiten sagen es,
  und der Prüfbericht des Imports nennt die Zahl der geänderten Haushalte.
- Jede Änderung steht im Änderungsprotokoll.

## Begründung

Der Admin braucht für Korrekturen nicht auf den nächsten Import zu warten. Weil der Import
unverändert ersetzt, bleibt das Altsystem bis zum Umstieg führend; die Warnungen verhindern,
dass Änderungen unbemerkt verloren gehen. Beim späteren Umstieg wird einfach nicht mehr
importiert.
