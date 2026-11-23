# ADR 0169: Warnung, wenn die Festplatte des Servers voll wird

## Problem

Ist die Festplatte des Servers voll, kann bintafeln nichts mehr speichern: keine Abholung, keine
Quittung, keine Sicherung. Bisher zeigte „Speicher und Fotos“ nur, wie viel bintafeln selbst
belegt. Wie voll die Platte insgesamt ist, sah man nur beim Anbieter – und niemand wurde gewarnt.

## Entscheidung

- bintafeln liest den freien Platz der Platte, auf der seine Dateien liegen (`MEDIA_ROOT`), mit
  Bordmitteln aus (`shutil.disk_usage`, `apps/core/speicherplatz.py`). Ein Zugang zum Konto des
  Anbieters ist nicht nötig; es gibt keine neue Abhängigkeit.
- „Speicher und Fotos“ zeigt oben einen Balken: belegt, frei, Anteil.
- Zwei einstellbare Grenzen (`SpeicherWarnung`, Vorgabe: Warnung unter 20 % frei, dringend unter
  10 % frei). Darunter
  - sehen alle mit dem Recht `einstellungen.tafel` einen Hinweis auf der Startseite (dringend:
    rot), und
  - es geht **einmal je Stufe** eine Mail an die unter „Mail-Empfänger“ gewählten Personen
    (Benachrichtigung `speicher_knapp`, nicht abschaltbar wie das Sicherheitsupdate). Ist wieder
    genug frei, beginnt es von vorn.
- Geprüft wird beim Besuch der Startseite und alle fünf Minuten mit dem Versand der gesammelten
  Benachrichtigungen – also auch, wenn niemand angemeldet ist.

## Begründung

Der Füllstand lässt sich im Programm selbst lesen; das ist einfacher und sicherer als eine
Anbindung an den Anbieter und funktioniert bei jedem Hoster und im eigenen Netz. Gemessen wird
bewusst die ganze Platte, nicht nur der Anteil von bintafeln: Voll ist voll, egal wodurch.
Sicherungen an einem anderen Ort (Online-Speicher, zweite Platte) sieht bintafeln nicht; das
steht auf der Seite. Eine Mail je Stufe statt täglich, damit die Warnung ernst genommen wird.
