# 0094 – Datenschutz, Impressum und Einverständnis als interner Text

## Problem

Das Antragsformular verweist über externe Links auf Datenschutzerklärung, Impressum und
Einverständniserklärung der Tafel. Nicht jede Tafel hat dafür eine eigene Webseite oder ein
passendes PDF; manche möchten diese Texte lieber direkt im Programm pflegen.

## Entscheidung

- Die Texte gehören der **ganzen Tafel**, nicht nur dem Antragsmodul. `TafelEinstellungen` bekommt
  je einen Textbereich `datenschutz_text`, `impressum_text` und `einverstaendnis_text` (HTML über
  den vorhandenen Editor, Bilder per Adresse). Bearbeitet werden sie unter
  „Einstellungen → Tafel → Rechtstexte“ (`core:rechtstexte`, Recht `einstellungen.tafel`).
- Ist ein Text gesetzt, führt der Link im Formular auf eine **interne, öffentliche Seite**
  (`antrag:rechtstext`, `AntragEinstellungen.rechtslink()` liest den Text aus den
  Tafel-Einstellungen); ist nur der externe Link gesetzt, bleibt dieser. Beides ist also weiter
  möglich, der interne Text hat Vorrang.
- Die **externen Links** als Rückfallebene bleiben bei den Antrags-Einstellungen
  (`AntragEinstellungen.datenschutz_url` usw.), weil sie zur Fußzeile und den Häkchen des Formulars
  gehören. `core` liest den Text selbst; `antraege` hängt (wie erlaubt) von `core` ab, nicht
  umgekehrt.
- Angezeigt wird der Text bereinigt über `apps.core.html.bereinigen()` (nh3); Skripte und
  gefährliche Attribute werden entfernt. Gespeichert wird roh, bereinigt erst beim Anzeigen.
- Die öffentliche Seite trägt das Logo und die Farben der Tafel, zeigt aber **nur den jeweiligen
  Text** – ohne die Sprachwahl des Antragsformulars (der Text ist einsprachig) und ohne die
  Fußzeile mit den anderen Links (`nur_rechtstext` in `oeffentlich.html`).
- Verschoben aus `AntragEinstellungen` nach `TafelEinstellungen` mit Migration
  `core 0023` (Felder) und `antraege 0018` (vorhandene Texte kopieren, dann entfernen – umkehrbar,
  ohne Datenverlust).

## Begründung

Tafeln ohne eigene Webseite können die Pflichttexte so ohne Umweg bereitstellen, ohne dass
bintafeln tafelspezifische Inhalte mitliefert. Die Entscheidung „interner Text vor externem Link“
hält die Oberfläche einfach: ein Feld ausfüllen genügt.
