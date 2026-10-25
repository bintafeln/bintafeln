# 0059: Konten der Ausgabestellen für Einlass-Tablets

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die Tablets am Einlass bedienen wechselnde Personen, die die Tafel teils nicht einmal kennt.
Persönliche Konten mit Zwei-Faktor-Anmeldung sind dafür zu umständlich; ein geteiltes persönliches
Konto verwischt dagegen, wer was darf.

## Entscheidung

- Jede Ausgabestelle kann genau ein Konto haben (`Benutzer.stelle`). Es wird unter
  „Team → Ausgabestellen-Konten“ angelegt, hat die Rolle Ausgabe und ist nur dieser
  Ausgabestelle zugeordnet (ADR 0034). Es erscheint nicht bei den Mitarbeitenden.
- Anmeldung mit dem Namen der Ausgabestelle (statt Benutzername) und Passwort; für diese Konten
  gilt keine Zwei-Faktor-Pflicht (`zwei_faktor.ist_pflicht`).
- Ausgleich für den fehlenden zweiten Faktor: Abmeldung nach 30 Minuten ohne Anfrage
  (`StellenKontoMiddleware`, die Seite lädt dann neu) und für alle Konten eine Sperre von
  15 Minuten nach 5 falschen Passwörtern.
- Das Konto gehört keiner Person: „Meine Daten“ (Auskunft nach Art. 15) gibt es dafür nicht.

## Begründung

Ein leichtes Login am Tablet hält den Einlass am Laufen; die Begrenzung auf eine Ausgabestelle,
die Rolle Ausgabe und die automatische Abmeldung halten den möglichen Schaden klein.
