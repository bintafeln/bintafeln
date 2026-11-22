# ADR 0153: Touren – drei Personen, Gast, ECO-Plattform

## Problem

Viele Touren sollen künftig zu dritt fahren, und immer wieder fährt jemand ohne eigenes Konto
für einen Tag mit. Der Fahrerplan kennt dafür Plätze und Gäste; in den Touren fehlte es an zwei
Stellen: Eigene und kurzfristige Touren hatten nur eine Auswahl „Wer fährt“ ohne Rollen und ohne
Gast, und am Handy ließ sich beim Tourstart kein Gast eintragen. Die Fahrdienstleitung musste
außerdem für einen kurzfristigen Wechsel aus der Tourenplanung in den Fahrerplan springen.
Daneben arbeiten manche Tafeln (auch) mit der ECO-Plattform und wollen von den Touren dorthin.

## Entscheidung

- **Eigene und kurzfristige Touren** bekommen feste Plätze: `Tour.fahrer`, `beifahrer`,
  `beifahrer2` und `gast` (Name ohne Konto). `Tour.personen` bleibt die Menge aller, die
  mitfahren (Mail, „Ihre Tour“), und folgt aus den Plätzen. Vorhandene Touren füllt die
  Migration aus „Wer fährt“ (in der Reihenfolge der Namen; in der Maske zu berichtigen).
- **Touren aus dem Fahrerplan:** Die Zahl der Plätze (Vorgabe drei) und die Mindestbesetzung
  stehen wie bisher im Fahrerplan. Neu: Die Seite der Tour in der Planung zeigt oben die
  Besetzung des nächsten Fahrtags und lässt sie **für einen Tag ändern** – Person wechseln oder
  Gast eintragen. Das läuft über dieselbe Regel wie am Handy (`start.aendern()`) und steht als
  `Ersatz` im Fahrerplan; es gibt weiter nur eine Quelle für „wer fährt“.
- **Gast am Handy:** Bei „Nein, ändern“ lässt sich je Beifahrerplatz ein Gast mit Namen
  eintragen. Auf dem Fahrerplatz steht nie ein Gast; niemand ersetzt sich selbst durch einen Gast.
- **ECO-Plattform:** eine Einstellung der Touren (`eco_plattform`, `eco_adresse`). Ist sie an,
  steht im Menü unter „Touren“ der Eintrag „ECO-Plattform ↗“ (`touren:eco` leitet weiter) – nicht
  mehr auf den Seiten der Touren. Mehr nicht: Touren, Stationen
  und Lieferscheine in bintafeln bleiben nutzbar, es werden keine Daten ausgetauscht.

## Begründung

- Feste Plätze statt einer Mehrfachauswahl zeigen auf einen Blick, wer fährt, und passen zu den
  Plätzen des Fahrerplans.
- Die Tagesänderung aus der Planung spart den Sprung in den Fahrerplan, ohne dessen Regeln
  (wer verfügbar ist, wer ausfällt) zu umgehen.
- Der Link zur ECO-Plattform ist bewusst nur ein Link: bintafeln bleibt unabhängig, und jede
  Tafel entscheidet selbst, was sie wo erledigt.

## Nachtrag: Die Mannschaft ändert am Tag selbst

Die Mannschaft muss kurzfristige Wechsel und Mitfahrer unterwegs selbst eintragen können, ohne
das Büro. Am Tag der Tour steht deshalb oben in der Tour ein deutlicher Knopf „Besetzung ändern,
Mitfahrer oder Gast eintragen“ (vorher ein kleiner Link, und nur bei Touren aus dem Fahrerplan):

- Tour aus dem Fahrerplan: wie bisher über `start.aendern()` als Ersatz für den Tag.
- Kurzfristige Tour von heute: `MannschaftForm` setzt Fahrer, Beifahrer, zweiten Beifahrer und
  Gast direkt an der Tour.

Es bleibt dabei: Ändern darf nur, wer auf der Tour eingetragen ist oder das Recht
`touren.besetzung` hat, und niemand nimmt sich selbst heraus. Regelmäßige eigene Touren ohne
Fahrerplan haben keine Besetzung je Tag; dort ändert weiter die Planung.

## Nachtrag: nur vor der Abfahrt

Der Knopf stand auch unterwegs zwischen den Angaben zur Fahrt und machte die Seite unübersichtlich.
Die Mannschaft ändert ihre Besetzung deshalb nur noch, bis die Fahrt begonnen hat
(`fahrten.heute()` liefert noch nichts). Danach fehlt der Knopf, und `views_touren.start` lehnt
eine Änderung ab; das Büro ändert weiter in der Planung.
