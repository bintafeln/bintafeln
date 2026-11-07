# ADR 0115: Warteliste-Aktionen auf der ganzen Antragsseite statt eigener Detailseite

## Problem

Ein Antrag aus der Warteliste öffnete bisher eine **eigene** Warteliste-Detailseite
(`warteliste:eintrag`) mit einer verkürzten Antragsübersicht plus den Warteliste-Aktionen
(Status/Wartezeit setzen, Einladen, Anmerkungen, ähnliche Haushalte). Wer denselben Antrag über
„Anträge“ öffnete, sah die **ganze** Antragsseite (alle Felder, Nachweise, Ausweisprüfung). Zwei
verschiedene Ansichten für denselben Antrag sind verwirrend; gewünscht ist überall dieselbe
Anzeige.

## Entscheidung

Es gibt nur noch **eine** Antragsseite (`antraege:antrag`). Die Warteliste zeigt ihre Aktionen als
zusätzlichen Abschnitt **auf dieser Seite**, über einen neuen Modul-Haken `Modul.antrag`
(`antrag(request, antrag) -> HTML`, analog zu `startseite`/`mein_konto`, aggregiert in
`apps/core/module.py`). So bleibt **kein modulspezifischer Code im Kern**: Die Antragsseite rendert
nur `module.antrag(request, a)`, die Warteliste liefert den Abschnitt (`apps/warteliste/modul.py`,
Vorlage `warteliste/_antrag_panel.html`) – nur, wenn der Antrag auf der Warteliste steht und man sie
sehen darf.

- Status setzen postet an `warteliste:status` (mit `zurueck` zur Antragsseite), Einladen an
  `warteliste:einladen`; beide gab es schon.
- „Ähnliche Haushalte im Kundenstamm“ lädt der Abschnitt **per htmx nach**
  (`warteliste:antrag_treffer`), damit die Antragsseite nicht auf den (teuren) Abgleich wartet.
  `abgleich_entscheiden` akzeptiert `weiter` jetzt auch auf `/antraege/`, sodass das Entscheiden zur
  Antragsseite zurückführt.
- Anmerkungen stehen ohnehin schon auf der Antragsseite (dasselbe `AntragAnmerkung`), daher ohne
  Dopplung.
- Die alte Adresse `warteliste:eintrag` bleibt als **Weiterleitung** auf `antraege:antrag`, damit
  vorhandene Links (Listen, Abgleich, Dubletten, Termine) weiter funktionieren.

## Begründung

Eine einzige, vollständige Antragsansicht ist für die Nutzenden klarer und spart eine doppelt
gepflegte Seite. Der Modul-Haken hält die Trennung Kern/Modul ein (ADR 0049); das Nachladen der
ähnlichen Haushalte hält die Antragsseite schnell (wie bei Abgleich/Dubletten, ADR 0109).
