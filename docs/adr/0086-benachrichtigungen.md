# 0086 – Benachrichtigungen: Häufigkeit je Person, Erledigtes entfällt

## Problem

bintafeln schickt Mitarbeitenden Mails: neuer Antrag, Korrekturwunsch vom Einlass, Ausfall
oder Gesundmeldung im Dienstplan und Fahrdienst, Sicherheitsupdate. Bei vielen Vorgängen
werden das sehr viele Mails, oft zu Dingen, die die Person inzwischen schon im Programm
erledigt hat.

## Entscheidung

- Alle Benachrichtigungen an Mitarbeitende laufen über
  `apps.core.benachrichtigung.melden(art, an, betreff, text, schluessel)`. Arten des Kerns
  stehen in `benachrichtigung.KERN`, Module bringen eigene über `Modul.benachrichtigungen`.
- Jede Person wählt selbst unter „Mein Konto → Benachrichtigungen“ je Art: sofort, stündlich,
  täglich oder wöchentlich gesammelt oder nie, dazu Uhrzeit und Wochentag. Ohne Wahl gilt
  „sofort“, also das bisherige Verhalten. Sicherheitsupdates lassen sich nicht abschalten,
  höchstens täglich sammeln.
- Gesammelte Meldungen warten als `Meldung`. Vor dem Versand fragt `Art.offen(schluessel)`,
  ob die Sache noch offen ist (Antrag noch neu, Korrekturwunsch noch offen, Ausfall noch ohne
  Ersatz). Erledigtes fällt weg; bleibt nichts übrig, geht keine Mail. Je Person eine Mail.
  Verschickte und erledigte Meldungen werden gelöscht.
- Den Versand stößt `python manage.py benachrichtigungen_senden` an; der App-Container ruft es
  beim Webserver alle fünf Minuten auf (`docker/entrypoint.sh`). Kein Cronjob auf dem Server.
- Adressen ohne Konto (z. B. Helfer ohne Zugang) bekommen die Mail wie bisher sofort. Telegram
  bleibt sofort, weil es an eine Gruppe geht.

## Begründung

Die Person, die die Mails bekommt, weiß am besten, wie dringend sie sie braucht. Das Prüfen
kurz vor dem Versand macht Sammelmails nützlich: Sie enthalten nur, was noch zu tun ist. Ein
eigener Zeitgeber-Dienst wäre ein weiterer Container; die Schleife im App-Container genügt,
weil fünf Minuten Verzug nicht schaden.
