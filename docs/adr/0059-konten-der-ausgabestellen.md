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
- Das Konto gehört keiner Person. Darum fehlen ihm die persönlichen Funktionen unter „Mein Konto“:
  „Meine Daten“ (Auskunft nach Art. 15), das eigene Passwort ändern (das setzt der Admin auf der
  Seite der Ausgabestelle), die PIN für Aushang-Monitore (ADR 0080) und die Benachrichtigungen
  (ADR 0086; es bekommt keine). Die Ansichten sind dafür auch direkt gesperrt (`stelle_id`).
- Den Dienstplan (ADR 0077) sieht das Tablet-Konto nur, wenn ein Admin ihn für die Ausgabestelle
  ausdrücklich einschaltet (`Ausgabestelle.dienstplan_sichtbar`, Vorgabe aus). Technisch entzieht
  das Modul dem Konto dann das Recht `dienstplan.sehen`/`.planen` über den Modul-Hook
  `rechte_entzug` (greift in `rollen.rechte_von`, also auch für Menü und Ansichten), damit kein
  modulspezifischer Code in den Kern wandert (ADR 0049).
- Zwei-Faktor können diese Konten nur einrichten, wenn die Tafel es in den Anmelde-Einstellungen
  freischaltet (`AnmeldeEinstellungen.stellen_zwei_faktor`, Vorgabe aus); sonst fehlt der
  Abschnitt unter „Mein Konto“. Beim Ausschalten werden eingerichtete Geräte entfernt, damit die
  Anmeldung am Tablet nicht an einem Code hängt.

## Begründung

Ein leichtes Login am Tablet hält den Einlass am Laufen; die Begrenzung auf eine Ausgabestelle,
die Rolle Ausgabe und die automatische Abmeldung halten den möglichen Schaden klein.
