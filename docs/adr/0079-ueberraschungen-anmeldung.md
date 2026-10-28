# 0079: Überraschungen auf der Anmeldeseite an Festtagen

- Status: Angenommen
- Datum: 2026-10-28

## Problem

Die Anmeldeseite sieht jeden Tag gleich aus. Für die Ehrenamtlichen wäre an Festtagen eine kleine,
freundliche Überraschung schön – ohne die Anmeldung zu stören oder zusätzliche Abhängigkeiten.

## Entscheidung

- `apps/core/anlaesse.py` bestimmt den Anlass eines Tages: Halloween (24.–31.10.), Karneval
  (Weiberfastnacht bis Veilchendienstag, aus dem Ostersonntag in `apps/core/feiertage.py`), Ostern
  (Palmsonntag bis Ostermontag), Nikolaus (5./6.12.) und Weihnachten (20.–26.12.).
- Die Figuren (Fledermaus, Luftschlange, Osterhase, Nikolaus im Schlitten) sind selbst gezeichnete
  SVG-Symbole in `templates/includes/anlass.html`, bewegt nur mit CSS-Animationen: kein JavaScript,
  keine Bilddateien, nichts von außen. Jede Animation läuft einmal je Aufruf.
- Die Ebene liegt über der Seite, nimmt aber keine Klicks an (`pointer-events: none`) und ist für
  Screenreader ausgeblendet (`aria-hidden`). Bei „Bewegung reduzieren“ im Betriebssystem bleibt sie
  aus.
- Abschaltbar in den Anmelde-Einstellungen (`AnmeldeEinstellungen.ueberraschungen`, an).
  `?anlass=<name>` zeigt einen Anlass zur Vorschau.
- Zufallswerte (Höhe, Verzögerung, Farbe) kommen als Text mit Punkt in die Vorlage, weil die
  deutsche Zahlenformatierung sonst ein Komma schreibt und CSS den Wert verwirft.

## Begründung

Reines CSS mit eingebetteten SVGs ist klein, wartbar, ohne neue Abhängigkeit und ohne Folgen für
Datenschutz oder Barrierefreiheit. Die Anmeldung bleibt voll bedienbar.
