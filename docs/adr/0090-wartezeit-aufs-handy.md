# 0090 – Wartezeit aufs Handy

## Problem

Kunden möchten auf dem eigenen Handy sehen, wie viele noch vor ihnen sind und wann sie dran
sind. Eine Tafel hat viele Ausgabestellen, oft ohne Monitor. Links dürfen nicht im Netz
kursieren, und Kunden einer Ausgabestelle sollen nichts von anderen Ausgabestellen sehen. Neue
Ausweise mit QR-Code für alle Kunden zu drucken, ist zu teuer.

## Entscheidung

- Öffentliche Seite `/warten/` im Modul Aufruf (ADR 0050), zentral geschaltet über
  `HandyEinstellungen.modus`: aus, an allen Ausgabestellen mit Aufruf oder nur an ausgewählten
  (`AufrufEinstellungen.handy`, gewählt im selben Abschnitt über `HandyForm.stellen`). Ein fester Aushang mit QR-Code (PDF unter „Aufruf, Monitor und
  Kiosk“) führt dorthin; er ist kein Geheimnis und gilt an allen Ausgabestellen.
- Einmalige Anmeldung mit **Kundennummer und Geburtsdatum der Hauptperson**. Danach liegt im
  Handy ein zufälliger Schlüssel als Cookie (gespeichert nur als Prüfsumme in `HandyZugang`,
  an der Kundennummer). Höchstens `HandyEinstellungen.geraete` Handys je Haushalt (Vorgabe 2); am Einlass
  setzt „Handys zurücksetzen“ sie zurück. Fehlversuche sind je Adresse begrenzt (8 je Stunde).
- Die Seite zeigt nur den eigenen Platz an der **Ausgabestelle des Haushalts** (aus der
  Kundengruppe), nie Namen oder andere Nummern: „noch 7 vor Ihnen, ca. 20 Minuten“, „Bitte jetzt
  eintreten“, „schon aufgerufen“, „heute schon da“. Die Schätzung kommt aus den letzten
  Aufrufen des Tages. Die Seite lädt sich alle 30 Sekunden neu, ohne JavaScript, in den 29
  Sprachen des Antragsformulars (`apps/aufruf/warten_texte/`); der Sprachhinweis
  (`sprachhinweis.js`) schlägt nach dem Anmelden die Sprache zur Staatsangehörigkeit vor.
- Optional ein persönlicher QR-Code auf **neu gedruckten** Ausweisen (Element „QR-Code Wartezeit
  aufs Handy“ in der Ausweis-Vorlage, Hook `Modul.ausweis_qr`): jeder Druck erzeugt einen neuen
  Code (`HandyCode`), der alte gilt nicht mehr; er richtet das Handy ohne Geburtsdatum ein, die
  Grenze der Handys gilt auch hier. Nur mit öffentlicher Adresse (`BINTAFELN_DOMAIN`).
- Handys und Code stehen in der Auskunft zum Haushalt (Hook `Modul.auskunft_haushalt`).
- Der Modulrahmen bekommt `Modul.weitere_urls` für Adressen außerhalb des ersten Pfads.

## Begründung

Ein geheimer Link pro Ausgabestelle würde weitergegeben. Das Geheimnis liegt deshalb bei den
Kunden selbst (Kundennummer und Geburtsdatum), der Aushang darf öffentlich sein. Die
Handy-Bindung macht weitergegebene Zugänge wertlos, und die Anzeige verrät ohnehin nur einen
Platz ohne Namen. Die Ausweise bekommen den Code nach und nach, ohne Sonderdruck.
