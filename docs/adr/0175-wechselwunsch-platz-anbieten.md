# ADR 0175: Platz per E-Mail anbieten, der Kunde bestätigt über einen Link

## Problem

Ein Wechselwunsch (ADR 0173) ließ sich nur genehmigen oder ablehnen. Oft ist aber erst später
ein Platz frei, und die Verwaltung will wissen, ob der Kunde ihn dann noch möchte, bevor sie
ihn umsetzt – bisher ging das nur mit einem Anruf.

## Entscheidung

- Auf der Seite „Wechselwünsche“ gibt es je offenem Wunsch **„Platz anbieten“** (Recht
  `kunden.wechsel_entscheiden`): Kundengruppe, „Wechsel ab“, freier Zusatz. Der Kunde bekommt
  eine E-Mail mit dem Angebot und zwei Knöpfen (Ja/Nein). Ohne E-Mail-Adresse geht es nicht.
- **Zugang ist allein der Link:** Er enthält einen zufälligen Schlüssel (`secrets.token_urlsafe`,
  256 Bit). Gespeichert wird nur dessen Prüfsumme; die Mail steht ohne Inhalt im Mail-Archiv
  (`vertraulich=True`). Eine zweite Abfrage (Geburtsdatum, Postleitzahl) gibt es bewusst nicht:
  Solche Angaben sind im Bestand teils falsch, und der Link gewährt nichts außer diesem einen
  Ja oder Nein.
- Die öffentliche Seite (`kunden:wechsel_angebot`) zeigt **nur das Angebot** – keinen Namen,
  keine Kundennummer. Bestätigt wird erst mit einem Knopf (POST), nicht schon durch das Öffnen:
  Mailprogramme und Virenscanner rufen Links von selbst auf.
- **„Ja“** führt den Wechsel aus wie eine Genehmigung (sofort oder als geplante Verlegung zum
  angebotenen Datum, Mail „genehmigt“, Notiz); als Entscheider steht, wer angeboten hat, mit dem
  Zusatz „vom Kunden bestätigt“. Mit dem Angebot hat die Verwaltung bereits entschieden.
- **„Nein“** ändert nichts; der Wunsch bleibt offen, die Antwort steht in der Liste und als Notiz.
- **Frist 7 Tage** (`wechsel.ANGEBOT_TAGE`). So lange ist der Platz **reserviert**
  (`gruppen.reservierte_zugaenge()` zählt laufende Angebote mit). Danach steht „keine Antwort“
  da; die Verwaltung kann neu anbieten – ein neues Angebot macht den alten Link ungültig.
- Regeln nur in `apps/kunden/wechsel.py` (`anbieten()`, `angebot_finden()`,
  `angebot_beantworten()`); die Felder `angebot_*` hängen am `Wechselwunsch` und werden mit ihm
  nach 90 Tagen gelöscht.

## Begründung

Ein unerratbarer, einmaliger Link ist für eine Zusage zu einem Abholtermin angemessen und für
die Kunden die kleinste Hürde. Das Reservieren verhindert, dass der angebotene Platz in der
Zwischenzeit vergeben wird; die kurze Frist verhindert, dass Plätze lange blockiert bleiben.
