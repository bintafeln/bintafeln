# ADR 0180: Ausweisdruck später zurücknehmen, Schwerbehinderte getrennt drucken

## Problem

Nach „Alle gemeldeten Ausweise drucken“ fragte ein Kasten sofort, ob alle Ausweise ordentlich aus
dem Drucker gekommen sind (ADR 0167). Wer von zu Hause über VPN druckt, kann das in dem Moment
nicht beantworten. Außerdem bekommen Schwerbehinderte einen anderen Ausweis, der nicht
standardmäßig im Drucker liegt; beim Sammeldruck wurden sie trotzdem mitgedruckt und als erledigt
abgehakt.

## Entscheidung

- **Keine Nachfrage mehr.** Statt des Kastens steht auf „Nachrichten der Ausgabestellen“ der
  ruhige Abschnitt „Zuletzt gedruckte Ausweise“: die letzten Drucke (höchstens fünf, höchstens
  14 Tage alt) mit **„Druck zurücknehmen“**. Wer nichts tut, lässt den Druck gelten; „ausblenden“
  nimmt einen Eintrag sofort weg (`an_stelle.letzte_drucke()`).
- **Jeder Druck gemeldeter Ausweise** lässt sich so zurücknehmen – auch der einzelne Ausweis und
  der Sammeldruck aus der Kundenliste, sofern er eine Meldung erledigt hat.
- **Schwerbehinderte getrennt:** Sind unter den gemeldeten Haushalte, deren Ausweis das
  Rollstuhl-Symbol trägt (`merkmale.mit_rollstuhl_ausweis()`), gibt es zwei Knöpfe: „ohne
  Schwerbehinderte“ und „nur Schwerbehinderte“. Was nicht im PDF ist, bleibt als Meldung offen.
- Das Zurücknehmen selbst bleibt wie in ADR 0167 (`druck_zuruecknehmen()`).

## Begründung

Ob Papier herauskam, weiß man oft erst später; eine Frage, die man nicht beantworten kann, hilft
nicht. Der Normalfall braucht jetzt keinen Klick, der Fehlerfall einen. Die Trennung richtet sich
nach dem Symbol auf dem Ausweis, nicht nach einem festen Feldnamen – so gilt sie auch für eigene
Merkmale einer Tafel.
