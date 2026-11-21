# ADR 0148: Touren – Stationsfolge, Besetzung und die Ansicht für unterwegs

## Problem

Die Stationen (ADR 0147) müssen zu Touren werden, die Fahrer am Handy abfahren. Der Fahrdienst
(ADR 0074) kennt schon „Touren“, aber nur als Personalplan: wer an welchem Wochentag auf welchem
Platz sitzt. Die Tafel braucht außerdem Touren, die nicht im Fahrerplan stehen, und kurzfristige
Touren für einen Tag, die die Fahrdienstleitung den Fahrern oder Angestellten schickt.

## Entscheidung

- **`touren.Tour` ist die Stationsfolge, `fahrdienst.Tour` bleibt der Personalplan.** Eine
  Abholtour kann auf eine Tour des Fahrerplans zeigen (`fahrdienst_tour`); dann kommen Fahrtage
  und Besetzung von dort (`plan.tage()`, also mit Ersatz und Ausfall). Ohne den Verweis ist es
  eine eigene Tour mit eigenen Fahrtagen und Personen. Mit `datum` ist es eine kurzfristige Tour
  nur für diesen Tag. Ist das Modul Fahrdienst ausgeschaltet, gilt jede Tour als eigene Tour.
- **`Halt`** verbindet Tour und Station mit `reihenfolge` und optionalen Wochentagen (eine
  Bäckerei nur samstags). Eine Station steht je Tour einmal. Nicht mehr angefahrene Stationen
  (`aktiv` aus) fallen unterwegs heraus, bleiben aber in der Planung sichtbar.
- **Regeln ohne Oberfläche** in `apps/touren/ablauf.py`: `faehrt_am()`, `touren_am()`,
  `halte()`, `besetzung()`, `meine()`, `routen()`, `senden()`.
- **Ansicht für unterwegs zuerst fürs Handy:** „Touren heute“ (eigene Tour oben), darin je
  Station eine Karte mit großem Knopf „Navigation starten“. Wer heute fährt, hat die Tour über
  `Modul.startseite` auf der Startseite. Kein eigenes JavaScript.
- **Route der ganzen Tour** als Link zu Google Maps mit Zwischenstopps, ohne Startpunkt (=
  Standort). Google nimmt höchstens neun Zwischenstopps, im mobilen Browser ohne App nur drei;
  deshalb höchstens zehn Stationen je Link, längere Touren in Abschnitten. Der Hauptweg bleibt
  die Navigation je Station.
- **Kurzfristige und eigene Touren verschicken:** „An die Fahrer schicken“ meldet über die
  Benachrichtigung `touren_tour` (ADR 0086) an die gewählten Personen, mit Stationsliste und
  Link. Wählbar sind Fahrer, Beifahrer und Angestellte mit Konto. Touren aus dem Fahrerplan
  werden nicht verschickt; dort gilt der Fahrerplan.
- **Import `tourstationen.csv`** (`apps/touren/importieren_touren.py`): je Tour ersetzt die
  Datei die Stationsfolge; Touren werden über den Namen gefunden oder angelegt.
- **Rechte:** `touren.fahren` (Büro, Fahrer, Beifahrer) und `touren.planen` (Büro). Wer fahren
  darf, sieht alle Touren des Tages, nicht nur die eigene – wie beim Fahrerplan.
- **Frist:** Kurzfristige Touren werden 90 Tage nach ihrem Tag gelöscht. Die Auskunft nach
  Art. 15 nennt die Touren, bei denen eine Person unter „Wer fährt“ steht.

## Begründung

- Zwei getrennte Modelle statt einer Erweiterung von `fahrdienst.Tour`: Der Fahrdienst bleibt
  ohne das Modul Touren nutzbar und umgekehrt, und Touren ohne Personalplan brauchen kein
  Scheinobjekt im Fahrerplan.
- Der Stand einer Fahrt („Station erledigt“) fehlt hier bewusst; er kommt mit den Lieferscheinen,
  weil er dort entsteht.
- Der Link ohne Startpunkt vermeidet eine Standortabfrage in bintafeln.
