# ADR 0170: Geburtstagsbrief auf der Startseite

## Problem

Der Geburtstagskalender und die Kachel „Nächste Geburtstage“ zeigen Geburtstage nur,
wenn man hinsieht. Der Vorstand möchte keinen Geburtstag im Team verpassen, und wer selbst
Geburtstag hat, soll vom Programm einen Glückwunsch bekommen.

## Entscheidung

- Hat ein Mitarbeitender **heute oder gestern** Geburtstag, legt sich auf der **Startseite** ein
  Brief über die Seite – gebaut wie der rote Brief der Touren (ADR 0159), aber festlich: bunter
  Umschlag mit Torte und Konfetti, kein Rütteln, kein Ton. Bei `prefers-reduced-motion` bewegt
  sich nichts; der Nachtmodus hat eigene Farben. Er erscheint nur auf der Startseite, nicht über
  jeder Seite.
- **Wer ihn sieht:** das Geburtstagskind seinen eigenen Glückwunsch; wer das neue Recht
  `mitarbeitende.geburtstagsbrief` hat, den Brief zu allen Mitarbeitenden (mit Alter). Das Recht
  ist für den Vorstand gedacht. Weil der Code keine Rollennamen kennt (ADR 0033), hat es in den
  Vorgaben nur der Admin; die Tafel gibt es der passenden Rolle selbst.
- Mitarbeitende zählen wie im Kalender (`geburtstage._mitarbeitende`: aktives Konto, kein
  Ausgabestellen-Konto, Geburtsdatum an der Adresse); der 29.02. wird sonst am 28.02. gefeiert.
- **Einmal je Konto und Geburtstag:** „Gratuliert“ (beim eigenen „Danke!“) legt einen
  `konten.GeburtstagGruss` (Konto, Adresse, Tag) an. „Später“ und Esc schließen nur bis zum
  nächsten Besuch der Startseite. Die Ansicht merkt nur fürs eigene Konto und nur, was ihm
  gerade als Brief zusteht.
- Die Merker sind vorübergehend: nach 30 Tagen gelöscht (`geburtstage.fristen_anwenden`, beim
  Aufruf der Startseite), nicht in der Datensicherung, nicht im Änderungsprotokoll.
- Schalter `TafelEinstellungen.geburtstagsbrief` (Vorgabe an).
- Logik nur in `apps/konten/geburtstage.py` (`brief()`, `gesehen()`, `fristen_anwenden()`).

## Begründung

Der Brief über der Seite ist bekannt und wird gesehen; die festliche Form macht klar, dass es
kein Alarm ist. Gestern zählt mit, damit ein Geburtstag am Wochenende oder an einem Tag ohne
Anmeldung nicht untergeht. Das Alter steht nur im Brief an Berechtigte, nicht im eigenen
Glückwunsch. Gemerkt wird in der Datenbank und nicht im Browser, damit der Brief auf dem Handy
nicht noch einmal kommt, wenn man am PC schon bestätigt hat.
