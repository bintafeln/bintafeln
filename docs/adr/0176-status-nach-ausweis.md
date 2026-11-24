# ADR 0176: Status nach dem Ausweis, neuer Status „verstorben“

## Problem

Sehr viele Kunden standen auf „aktiv“, obwohl ihr Ausweis längst abgelaufen war: „aktiv“ hieß
nur, dass niemand etwas anderes eingetragen hatte (auch der Import setzt „leer = aktiv“). Der
Ablauf des Ausweises nahm zwar die Kundengruppe weg (ADR 0061) und sperrte am Einlass, änderte
aber nie den Status. Listen und Zählungen nach „aktiv“ sagten deshalb wenig. Für verstorbene
Kunden gab es keinen eigenen Status.

## Entscheidung

- **Wer keinen gültigen Ausweis hat, ist nicht aktiv.** Ist `KundenEinstellungen.status_nach_ausweis`
  an, setzt das Programm einen aktiven Kunden ab dem Tag nach dem Ablauf auf **„pausiert“**; wird
  der Ausweis verlängert, ist er wieder **„aktiv“**. Kein automatisches „beendet“.
- **Von Hand bleibt von Hand:** `Haushalt.status_automatisch` merkt, dass das Programm pausiert
  hat. Nur solche Kunden werden wieder aktiv. Wer von Hand pausiert, gesperrt, beendet oder als
  verstorben eingetragen ist, wird von der Automatik nie angefasst.
- Ohne eingetragenes Ablaufdatum bleibt ein Kunde aktiv (unbekannt ist nicht abgelaufen, wie in
  ADR 0061).
- **Wann:** sofort nach jeder Änderung im Programm (`gruppen.pruefen()` ruft `status.pruefen()`),
  täglich und nach dem Import (`gruppen.regel_anwenden()` ruft zuerst `status.regel_anwenden()`),
  und beim Einschalten für den ganzen Bestand. Jede automatische Änderung steht in der Historie.
- **Schalter, Vorgabe aus:** Ein Update stellt nichts von selbst um. Die Einstellungsseite nennt
  vorher, wie viele Kunden es beträfe.
- **Neuer Status „verstorben“** (von Hand). Er zählt wie „beendet“ nirgends mehr mit
  (`Haushalt.NICHT_MEHR`). `Haushalt.status_seit` hält fest, seit wann ein Status gilt; nach
  `KundenEinstellungen.verstorben_loeschen_monate` (Vorgabe 3, 0 = nie) legt
  `status.verstorbene_entfernen()` den Haushalt in den Papierkorb (wiederherstellbar, ADR 0073).
- Regeln nur in `apps/kunden/status.py`.

## Begründung

Der Status soll sagen, was am Einlass gilt. Sofort statt mit Kulanzfrist, weil Kundengruppe und
Ampel ohnehin am selben Tag reagieren. Kein automatisches „beendet“, weil das Ende einer
Kundschaft eine Entscheidung ist und kein Fristablauf. Der Papierkorb statt endgültigem Löschen
schützt vor einem versehentlich gesetzten „verstorben“.

## Nachtrag (2026-11-24): Eine Sperre geht vor

Eine eingetragene, laufende **Sperre** (`Sperre`, mit Von/Bis und Begründung) war bisher vom
Status unabhängig: Ein gesperrter Kunde mit abgelaufenem Ausweis wäre „pausiert“ worden. Jetzt
gilt die Reihenfolge **Sperre → Ausweis**: Wer eine laufende Sperre hat, steht auf „gesperrt“
(auch mit gültigem Ausweis, auch wenn das Programm ihn zuvor pausiert hatte); endet die Sperre,
gilt wieder der Ausweis (aktiv oder pausiert). `status_automatisch` merkt jetzt beides –
vom Programm pausiert oder gesperrt. Ein von Hand gesetztes „gesperrt“ ohne Sperre-Eintrag
bleibt wie jeder von Hand gesetzte Status unberührt.

