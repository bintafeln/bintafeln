# 0094 – Datenschutz, Impressum und Einverständnis als interner Text

## Problem

Das Antragsformular verweist über externe Links auf Datenschutzerklärung, Impressum und
Einverständniserklärung der Tafel. Nicht jede Tafel hat dafür eine eigene Webseite oder ein
passendes PDF; manche möchten diese Texte lieber direkt im Programm pflegen.

## Entscheidung

- `AntragEinstellungen` bekommt je einen Textbereich `datenschutz_text`, `impressum_text` und
  `einverstaendnis_text` (HTML über den vorhandenen Editor, Bilder per Adresse).
- Ist ein Text gesetzt, führt der Link im Formular auf eine **interne, öffentliche Seite**
  (`antrag:rechtstext`, `AntragEinstellungen.rechtslink()`); ist nur der externe Link gesetzt,
  bleibt dieser. Beides ist also weiter möglich, der interne Text hat Vorrang.
- Angezeigt wird der Text bereinigt über `apps.core.html.bereinigen()` (nh3); Skripte und
  gefährliche Attribute werden entfernt. Gespeichert wird roh, bereinigt erst beim Anzeigen.
- Bearbeitet wird unter „Anträge → Formular einstellen → Rechtstexte bearbeiten“
  (`einstellungen.antraege`). Die öffentliche Seite trägt das Logo und die Farben der Tafel.

## Begründung

Tafeln ohne eigene Webseite können die Pflichttexte so ohne Umweg bereitstellen, ohne dass
bintafeln tafelspezifische Inhalte mitliefert. Die Entscheidung „interner Text vor externem Link“
hält die Oberfläche einfach: ein Feld ausfüllen genügt.
