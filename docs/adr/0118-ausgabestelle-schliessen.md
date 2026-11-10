# ADR 0118: Ausgabestelle schließen mit Enddatum und geplanter Kundenverlegung

## Problem

Eine Ausgabestelle kann ihren Betrieb einstellen. Dann muss sie zu einem Stichtag wegfallen
(ins Archiv), und die dort betreuten Kunden müssen vorher geordnet auf andere Ausgabestellen
bzw. Kundengruppen verteilt werden – ohne dass am Schließtag jemand ohne Gruppe dasteht.

## Entscheidung

- **Enddatum:** `Ausgabestelle.schliesst_am` (letzter Ausgabetag). Ab dem Tag danach schiebt die
  tägliche Regel `verlegung.stellen_schliessen()` die Stelle automatisch ins Archiv (`aktiv=False`)
  und setzt ihre Kundengruppen inaktiv. Das Enddatum wieder zu leeren hebt das auf (wieder aktiv
  setzen von Hand).
- **Geplante Verlegung je Haushalt:** `GeplanterWechsel` (Haushalt, Ziel-Kundengruppe, `ab`-Stichtag,
  `erledigt_am`), höchstens einer offen je Haushalt. Die Seite „Kunden verlegen“ (Recht
  `kunden.bearbeiten`) listet die aktiven Haushalte der schließenden Stelle und lässt je Haushalt
  eine Ziel-Kundengruppe und einen gemeinsamen Stichtag wählen.
- **Ausführung:** `verlegung.anwenden()` setzt am Stichtag die neue Kundengruppe, hält den Wechsel
  in der Historie fest (`HaushaltEreignis`, Quelle „automatisch“) und wendet die Ausweis-Regel
  (ADR 0061) an; eine inzwischen inaktive Zielgruppe bleibt offen. Beide Funktionen laufen täglich
  über `kunden.models.fristen_anwenden()` (Startseite).
- **Stichtag-Vorgabe:** Die Verlegungsseite schlägt den **Tag nach dem letzten Ausgabetag**
  (`schliesst_am + 1`) als Stichtag vor – erst ab dann gilt die neue Stelle; der Tag bleibt
  änderbar.
- **Anzeige am Haushalt:** Ein offener geplanter Wechsel steht auch in der Kundenmaske
  („Geplanter Umzug: ab … zu …“), nicht nur auf der Verlegungsseite.
- **Neuer Ausweis:** Am Umzugstag legt `verlegung.anwenden()` je verlegtem Haushalt automatisch
  eine `Notiz` „Ausweis drucken (Umzug zu …)“ an, damit beim nächsten Einlass ein neuer Ausweis
  gedruckt wird (die neue Ausgabestelle/Gruppe steht darauf).
- **Platzreservierung:** Ein geplanter, noch nicht ausgeführter Zuzug belegt den Platz in der
  Zielgruppe, sobald sein Stichtag in die Vorlaufzeit fällt
  (`KundenEinstellungen.verlegung_vorlauf_wochen`, Vorgabe 6 Wochen; 0 = erst am Stichtag). Weit im
  Voraus geplante Umzüge blockieren den Platz noch nicht, denn so früh lässt sich ohnehin noch
  nichts umsetzen. `gruppen.reservierte_zugaenge()` liefert die Zahl der so reservierten Zuzüge je
  Gruppe; `gruppen.mit_plaetzen()` und `aufnahme.freie_gruppen()` ziehen sie von den freien Plätzen
  ab, so dass derselbe Platz nicht bis zum Stichtag ein zweites Mal vergeben wird (sonst drohte eine
  Überbuchung ab dem Stichtag).

## Begründung

Die Verteilung je Haushalt gibt der Tafel volle Kontrolle (verschiedene Kunden können in
unterschiedliche neue Gruppen). Der gemeinsame Stichtag und das Enddatum trennen „Plan“ von
„Ausführung“: bis zum Stichtag ist alles änderbar, danach passiert es automatisch und
nachvollziehbar in der Historie. Das Archivieren über dieselbe tägliche Regel wie die übrigen
Fristen hält die Logik an einer Stelle.
