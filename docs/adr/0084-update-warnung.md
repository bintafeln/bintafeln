# 0084: Warnung bei wichtigen Updates

- Status: Angenommen
- Datum: 2026-10-29

## Problem

Tafeln, die lange nicht aktualisieren, verpassen Sicherheitskorrekturen. Eine Warnung allein nach
dem Alter der installierten Version wäre aber lästig: Die meisten Versionen bringen nur
Kleinigkeiten, und wer ständig gewarnt wird, liest die Warnung nicht mehr.

## Entscheidung

- Jede Version bekommt eine Stufe: `sicherheit`, `wichtig`, `neu` oder `klein` (Vorgabe). Sie
  kommt aus dem Label des Pull Requests (`sicherheit`, `wichtig`, `neue-funktion`).
  `.github/workflows/version.yml` legt dafür ein annotiertes Tag mit der Zeile `stufe=…` an.
- Wird eine Lücke erst später bekannt, steht sie in `docs/sicherheitshinweise.txt` auf `main`
  („VERSION Text“, VERSION = erste Version ohne die Lücke).
- Der Dienst `updater` liest beides bei jedem Abruf und schreibt es nach `versionen.txt`
  (`stufe=…`, `sicherheit=…`), dazu den Zeitpunkt des letzten gelungenen Abrufs
  (`erfolgreich=…`).
- `apps/core/update.warnung()` entscheidet:
  - Sicherheit: sofort;
  - wichtige Korrektur: nach 7 Tagen;
  - fehlgeschlagener Abruf: nach 14 Tagen;
  - neue Funktionen: nach 30 Tagen;
  - klein: nie.
- Die Warnung sehen alle mit dem Recht `system.update` auf der Startseite. Nur den Hinweis auf
  neue Funktionen kann man für 30 Tage ausblenden.
- Bei einem Sicherheitsupdate geht einmal je Update eine Mail an alle mit dem Recht.

## Begründung

- Die Stufe muss in Git stehen, weil Installationen nur Git abrufen und GitHub nicht direkt
  fragen.
- Ein Label wählt der Maintainer beim Mergen mit einem Klick.
- Die Datei auf `main` erreicht auch Installationen mit alter Version, ohne Tags umzuschreiben.
- Die Mail geht beim Aufruf der Startseite durch irgendjemanden hinaus. So braucht es keinen
  eigenen Zeitplan, und sie kommt auch an, wenn niemand mit Update-Recht vorbeischaut.
