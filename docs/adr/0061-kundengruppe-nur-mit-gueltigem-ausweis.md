# 0061: Kundengruppe nur mit gültigem Ausweis

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Kundengruppen haben ein Maximum an Haushalten. Pausierte, gesperrte oder beendete Kunden und
Kunden mit abgelaufenem Ausweis belegen dort Plätze, obwohl sie nicht kommen. Neue Kunden finden
dann keine freie Gruppe, oder das Maximum wird überschritten. Außerdem fehlte, von wann bis wann
ein Kunde in welcher Gruppe war.

## Entscheidung

- Ohne gültige Kundenkarte keine Kundengruppe: Wer pausiert, gesperrt oder beendet ist oder
  dessen „Ausweis gültig bis“ vor heute liegt, verliert die Kundengruppe
  (`apps/kunden/gruppen.py`). Ohne Datum bleibt die Gruppe (unbekannt ist nicht abgelaufen).
- Wann: bei jeder Änderung im Programm sofort (Bearbeiten, Neuer Haushalt, Aufnahme) mit
  Meldung; beim Import vor dem Festhalten der Historie (sonst stünde bei jedem Import „hinein“
  und „hinaus“); täglich bei den Fristen für abgelaufene Ausweise (Historie mit Quelle
  „automatisch“ und Grund).
- Standard ist an; Tafeln, die Kunden in der Gruppe lassen wollen, schalten es in den
  Kunden-Einstellungen ab (`KundenEinstellungen.gruppe_behalten`).
- `Gruppenzeit` hält je Kundennummer fest, von wann bis wann ein Kunde in welcher Gruppe war, und
  warum es endete. `zeiten_abgleichen()` vergleicht dafür den Kundenstamm mit den offenen Zeiten
  (nach Änderungen, Import und täglich). Bestehende Mitglieder bekommen bei der Einführung eine
  offene Zeit ohne Anfang. Die Zeiten hängen an der Kundennummer, stehen in der Auskunft und
  werden wie die Historie gelöscht.
- Die Regel ändert keine Haushalte per Migration; sie greift erst im Betrieb.

## Begründung

Das Maximum einer Kundengruppe ist nur verlässlich, wenn nur berechtigte Kunden Plätze belegen.
Eine Zuordnung, die automatisch entfällt, ist sicherer als eine Liste, die das Büro regelmäßig
aufräumen muss. Die Zeiten machen nachvollziehbar, wann ein Kunde welche Gruppe hatte.
