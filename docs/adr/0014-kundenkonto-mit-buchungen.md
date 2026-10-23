# 0014: Kundenkonto mit Buchungen

- Status: Angenommen
- Datum: 2026-10-24
- Ergänzt: ADR 0011, ADR 0013

## Problem

Kunden sollen im Voraus bezahlen können (z. B. für einen Monat). Spätere Abholungen werden dann
mit dem Guthaben verrechnet. Außerdem braucht die Tafel eine Kasse, die über Jahre und tageweise
rückwirkend abfragbar ist. Bisher gab es nur den Kontostand aus dem Import.

## Entscheidung

- Jede Bewegung ist eine **Buchung** mit Soll, Haben und dem dabei **bar** eingenommenen Betrag.
  Der Kontostand ändert sich um Haben − Soll. Der Kontostand aus dem Import ist der Anfangsstand.
- Arten von Buchungen:
  - **Abholung:** Der Beitrag steht im Soll. Je nach Zahlweise:
    - **aus Guthaben, Rest bar:** Guthaben wird verrechnet, ein Rest wird bar gezahlt.
    - **alles bar:** Das Konto bleibt unverändert.
    - **anschreiben:** nur wenn in den Einstellungen erlaubt; der Kontostand darf negativ werden.
      Die Ampel zeigt dann gelb.
  - **Einzahlung:** bar, ins Haben.
  - **Korrektur:** ohne Bargeld, nur Admin und Büro, mit Begründung.
- Der Empfang schlägt Vorauszahlungen vor (Rest dieses Monats, ganzer nächster Monat). Jeder
  Vorschlag erklärt, wie er entsteht: gezählte Tage, Kundengruppe, Höchstzahl, Ausweisablauf
  und was nicht berücksichtigt ist.
- Buchungen hängen am Haushalt **und** an der Kundennummer. Ein Neuimport löst die Verbindung
  zum Haushalt; der Kontostand kommt dann aus dem Import. Die Buchungen bleiben für die Kasse
  erhalten.
- **Fristen:** Nach der Frist für Abholungen (Vorgabe 3 Jahre) werden Buchungen anonymisiert,
  also ohne Haushalt, Kundennummer, Bemerkung und Namen. Nach der Buchungsfrist (Vorgabe
  10 Jahre) werden sie gelöscht.
- Die Kasse (Tag, Monat, Jahr, auch rückwirkend) wertet die Buchungen aus und folgt in einem
  eigenen Pull Request.

## Begründung

Soll/Haben/bar entspricht dem Kundenkonto im bisherigen Programm und trennt Bargeld sauber von
Verrechnung. Die Anonymisierung erfüllt die Löschfrist für personenbezogene Daten. Die
Kassenbeträge bleiben so lange, wie ein Verein Kassenunterlagen in der Regel aufbewahren muss.
Die genaue Frist legt die Tafel mit ihrer Kassenführung fest.
