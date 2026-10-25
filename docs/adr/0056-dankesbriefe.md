# 0056: Dankesbriefe an Spender mit Belegen

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Bisher entstanden Dankesbriefe in einem eigenen Programm: Word-Vorlage mit Textersetzung,
Umwandlung über LibreOffice, Zuwendungsbestätigungen aus dem Vereinsportal als PDF angehängt,
Einfach- und Mehrfachspender getrennt. Manche Tafeln stellen die Bestätigungen künftig in
bintafeln aus, andere weiter im Portal – beides soll gehen.

## Entscheidung

- Seite „Spenden → Dankesbriefe“ (Recht „Zuwendungsbestätigungen ausstellen“): Brieftext aus einer
  Serienbrief-Vorlage (ADR 0047) mit neuen Platzhaltern `{anzahl_spenden}` und `{spendendaten}`;
  Auswahl alle/Einfach-/Mehrfachspender eines Jahres, „nur noch nicht bedankt“.
- Anlagen wahlweise: Zuwendungsbestätigungen aus bintafeln (fehlende Geldspenden-Bestätigungen
  werden dabei ausgestellt) und hochgeladene Belege (`SpendenBeleg`, verschlüsselt über
  `apps.core.privatdateien`). Zuordnung über die Ziffern der Belegnummer im Dateinamen, sonst von
  Hand.
- Ausgabe als ein PDF (Brief und Anlagen je Spender hintereinander; zusammengefügt mit `pypdf`)
  oder als E-Mail mit PDF-Anhängen an Spender mit E-Mail-Einwilligung. `Spende.bedankt_am` und
  `SpendenBeleg.beigelegt_am` halten fest, was erledigt ist; der Versand steht wie bei Serienbriefen
  im Protokoll.
- Neue Abhängigkeit `pypdf` (reines Python, feste Version) nur zum Zusammenfügen von PDFs.

## Begründung

Vorlagen, Platzhalter, Briefformat und Bestätigungen gibt es schon; die Dankesbriefe verbinden sie
nur. Hochgeladene Belege machen bintafeln unabhängig davon, wo die Bestätigung entsteht. Ohne
LibreOffice und Word bleibt die Installation schlank.
