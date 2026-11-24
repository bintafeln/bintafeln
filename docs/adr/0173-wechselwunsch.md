# ADR 0173: Wechselwunsch eines Kunden („Will wechseln“)

## Problem

Kunden möchten am Einlass die Uhrzeit, den Tag oder die Ausgabestelle wechseln. Bisher wurde das
als freie Notiz aufgeschrieben: mal fehlte, wohin genau, mal war der Kunde danach nicht
erreichbar, und die Verwaltung musste die Wünsche in den Notizen suchen.

## Entscheidung

- Bei den Notizen eines Kunden steht der Knopf **„Will wechseln …“** (Recht `kunden.notizen`,
  also wer Notizen schreibt). Eine Seite grenzt den Fall Schritt für Schritt ein: Was soll sich
  ändern (Uhrzeit am selben Tag / anderer Tag / andere Ausgabestelle) → früher, später, egal
  bzw. welcher Tag, welche Ausgabestelle → **was dafür aktuell frei ist**
  (`aufnahme.freie_gruppen`, ohne die eigene und ohne interne Gruppen). Ist nichts frei oder
  passt nichts, wird der Wunsch trotzdem aufgenommen.
- **Erreichbarkeit:** Fehlen E-Mail-Adresse oder Telefonnummer, fragt die Seite danach und
  speichert sie am Haushalt (mit Historie). Ohne E-Mail-Adresse geht es nur mit dem Häkchen
  „hat keine E-Mail-Adresse“ und einem deutlichen Hinweis, dass nicht zurückgeschrieben werden
  kann; ganz ohne Kontakt wird nichts gespeichert.
- Der Wunsch ist ein eigener Datensatz `kunden.Wechselwunsch` an der Kundennummer (übersteht den
  Import) und steht zusätzlich als Notiz „Will wechseln: …“ beim Kunden. Je Kunde ist nur ein
  Wunsch offen.
- **Entscheiden** darf nur, wer das neue Recht `kunden.wechsel_entscheiden` hat (Vorgabe: nur
  Admin; die Tafel gibt es z. B. dem Vorstand). Liste unter „Kunden → Wechselwünsche“, Zahl im
  Menü und auf der Startseite. Genehmigen: Kundengruppe (vorbelegt: der Wunsch) und „Wechsel ab“
  (vorbelegt: heute). Heute zieht der Haushalt sofort um, ein späteres Datum wird als geplante
  Verlegung eingetragen. Ablehnen ändert nichts am Kunden.
- Der Kunde bekommt die Antwort per **E-Mail** (`mail.senden`, Art „Nachricht an einen Kunden“,
  auf der Seite „Mail-Empfänger“ aufgeführt); ohne Adresse oder bei einem Mailfehler steht das an
  der Entscheidung. Die Entscheidung steht auch als Notiz beim Kunden.
- Entschiedene Wünsche werden nach 90 Tagen gelöscht (`alte_wechselwuensche_loeschen()` in
  `fristen_anwenden()`); sie stehen in der Auskunft nach Art. 15 und im Änderungsprotokoll.
- Logik nur in `apps/kunden/wechsel.py`, Ansichten in `views_wechsel.py`.

## Begründung

Die geführte Abfrage sorgt dafür, dass die Verwaltung einen entscheidbaren Wunsch bekommt
(wohin, ab wann möglich, wie erreichbar), statt nachfragen zu müssen. Die Entscheidung bleibt
bei Vorstand oder Admin, weil ein Wechsel die Auslastung der Gruppen verändert. Ein eigenes
Recht statt eines Rollennamens folgt ADR 0033. Die kurze Aufbewahrung folgt der Datensparsamkeit:
Was gilt, steht danach ohnehin am Haushalt und in dessen Historie.
