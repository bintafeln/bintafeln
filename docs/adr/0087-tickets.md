# 0087 – Tickets: Meldungen mit Kategorie und Zuständigen

## Problem

Wer bei der Tafel etwas findet (Kühlung defekt, Waage kaputt, Fehler im Programm, Lager
undicht), sagt es heute irgendwem. Es geht verloren, oder niemand weiß, wer sich kümmert.

## Entscheidung

- Zuschaltbares Modul `tickets` (ADR 0049). Jede angemeldete Person eröffnet ein Ticket:
  Kategorie, Titel, Beschreibung, optional Fotos/PDF (verschlüsselt über
  `apps.core.privatdateien`).
- Der Admin (Recht `einstellungen.tickets`) legt Kategorien an und wählt je Kategorie
  **Personen** und **Rollen**, die benachrichtigt werden. Diese dürfen die Tickets der Kategorie
  auch bearbeiten; das Recht `tickets.bearbeiten` (Vorgabe Büro) gilt für alle Kategorien.
- Ein Ticket hat Status offen → in Arbeit → erledigt, eine zuständige Person (Auswahl aus den
  Konten) und Kommentare. Die meldende Person (und die zuständige) erfährt Antworten und
  Statuswechsel.
- Benachrichtigungen laufen über ADR 0086 (Arten `ticket_neu`, `ticket_antwort`): jede Person
  wählt, wie oft; „neues Ticket“ entfällt aus Sammelmails, sobald es jemand übernommen hat.
- Eigene Tickets sieht jede Person, fremde nur Zuständige. Erledigte Tickets werden nach einer
  einstellbaren Frist gelöscht (Vorgabe 365 Tage); „Löschen“ legt sie in den Papierkorb.
  Eigene Tickets stehen in der Auskunft nach Art. 15.

## Begründung

Kategorien mit Zuständigen bilden ab, wie Tafeln arbeiten (Technik, Lager, Fahrzeuge,
Programm). Rollen statt nur Einzelpersonen halten die Zuordnung aktuell, wenn Leute wechseln.
Die Benachrichtigungen aus ADR 0086 verhindern, dass Tickets in Mailfluten untergehen.
