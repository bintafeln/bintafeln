# 0096 – Übersichtslisten als PDF herunterladen und per E-Mail senden

## Problem

Die Übersichtslisten (Kunden, Adressbuch, Mitglieder, Spenden, Anträge) lassen sich als CSV für
Excel/LibreOffice herunterladen. Auf den Tablets der Ausgabe lässt sich CSV mangels passender
Software aber oft nicht öffnen. Gebraucht wird eine Alternative: dieselbe Liste als PDF (zum
Ansehen und Drucken, öffnet auf dem Tablet) und ein Weg, sie an einen anderen Rechner zu bringen.

## Entscheidung

- Ein gemeinsamer Helfer `apps/core/listenexport.ausliefern(request, titel, basisname, csv_text)`
  liefert dieselbe Liste je nach `aktion` (Auswahl-Formular, GET) als **CSV** (wie bisher, Vorgabe),
  als **PDF** (`pdf_aus_csv()`: der CSV-Text wird zu einer PDF-Tabelle quer, damit viele Spalten
  passen, über `apps.core.pdf`) oder **per E-Mail** (`aktion=mail`): die Liste geht als **PDF und
  CSV im Anhang** an die angegebene Adresse (`apps.core.mail.senden`), danach Weiterleitung mit
  Meldung auf die Liste.
- Jede Liste baut ihren CSV-Text wie bisher und reicht ihn an den Helfer; die Spaltenlogik bleibt
  je Liste. So ist das PDF genau die angezeigte/gefilterte Auswahl, die auch die CSV enthält.
- Die Knöpfe stehen gebündelt im gemeinsamen Baustein `templates/includes/listen_export.html`
  (CSV, PDF, E-Mail-Feld + Senden), eingehängt über das vorhandene Auswahl-Formular
  (`form="auswahl"`), sodass sie dieselbe Auswahl/Filterung wie der CSV-Export übernehmen. Das
  E-Mail-Feld ist mit der Adresse des angemeldeten Kontos vorbelegt, aber änderbar.
- **Alle drei Aktionen laufen über das GET-Auswahl-Formular.** Der E-Mail-Versand ist damit
  zwar ein Seiteneffekt per GET, wird aber nur durch den ausdrücklichen Knopf ausgelöst und
  leitet danach zurück (so wird beim Neuladen nicht erneut gesendet). Das hält die Filter- und
  Auswahl-Logik aller Listen unverändert, ohne POST-/CSRF-Sonderfälle je Liste.

## Begründung

Der Helfer erzeugt PDF und E-Mail aus dem bereits vorhandenen CSV-Text, statt jede Liste doppelt
aufzubauen – wenig Code, überall gleiches Verhalten. Das PDF deckt „ansehen/drucken“ (auch auf dem
Tablet) ab, die E-Mail das „auf einen anderen Rechner bringen“, und die CSV im Anhang bleibt für
die Weiterverarbeitung in Excel/LibreOffice erhalten.
