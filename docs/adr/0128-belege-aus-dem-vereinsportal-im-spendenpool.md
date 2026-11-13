# ADR 0128: Belege aus dem Vereinsportal im gemeinsamen Spendenpool

## Problem

ADR 0126 hielt die Belege aus dem Vereinsportal in eigenen Tabellen, getrennt von den Spenden in
bintafeln. Der Grund war richtig – für eine Spende darf es nur eine Zuwendungsbestätigung geben –,
die Folge aber nicht: zwei Spendenlisten, zwei Seiten für Dankesbriefe, Spender außerhalb des
Adressbuchs. Es sind dieselben Spenden. Dazu kam: Das Vereinsportal kann Sammelbescheinigungen für
Mehrfachspender weder mailen noch zuverlässig zusammenstellen. Die sollte bintafeln ausstellen,
und das geht nur mit Spenden im Spendenpool.

## Entscheidung

Jeder Beleg aus dem Vereinsportal wird eine `Spende` (Datum, Betrag, Belegnummer), der Spender
eine `Adresse`, das PDF ein `SpendenBeleg` an der Spende. `Spende.fremdbeleg` hält fest, dass es
schon einen Beleg aus einem anderen Programm gibt:

- **versendet:** Das andere Programm hat die Bescheinigung verschickt. bintafeln stellt nie eine
  eigene aus und schreibt keinen Dankesbrief.
- **offen:** Der Beleg liegt vor, ist dort aber nicht versendet.
  - *Eine* offene Spende des Spenders im Jahr: Der Beleg ist die Bescheinigung und liegt dem
    Dankesbrief bei; bintafeln stellt nichts aus.
  - *Mehrere* offene Spenden: bintafeln stellt eine Sammelbestätigung mit eigener Nummer aus
    (`bestaetigung.offene_geldspenden()`); die Einzelbelege liegen dann nicht bei
    (`dank._beizulegende()`).

Das Feld heißt bewusst neutral und liegt im Kern (`apps.spenden`); das Modul `vereinsportal`
setzt es nur. Es behält das Einlesen (Finanzexport, Spenderliste), den automatischen Abruf
(ADR 0127) und seine Einstellungen. Seine eigenen Listen, Dankesbriefe und hochgeladenen
Sammelbescheinigungen entfallen.

Die Liste „Spender mit E-Mail“ bleibt als Hilfsliste (`Kontakt`): Beim Einlesen kommen E-Mail,
Anrede und Versandweg zur Adresse. Wer nicht gespendet hat, kommt nicht ins Adressbuch.

Die Datenmigration `vereinsportal.0006` übernimmt schon eingelesene Belege samt verschlüsselter
Datei in den Spendenpool.

## Begründung

- **Ein Pool:** Spendenliste, Statistik, Serienbriefe, Auskunft nach Art. 15 und Papierkorb
  erfassen die Spenden ohne eigenen Code.
- **Die Regel verhindert die doppelte Bestätigung an der einen Stelle,** an der bintafeln
  Bestätigungen ausstellt, statt durch getrennte Datenhaltung.
- **Sammelbestätigung aus bintafeln:** Sie umfasst nur Spenden, deren Beleg im Vereinsportal
  nicht versendet ist. Ob die dort erzeugten, nicht versendeten Einzelbelege daneben bestehen
  dürfen, entscheidet die Tafel mit ihrer Steuerberatung; bintafeln legt sie in diesem Fall
  nicht bei.
- **Namen:** Auf dem Beleg steht der Spender als ein Stück. Das letzte Wort gilt als Nachname;
  Namen mit Rechtsform oder „Stiftung“, „Verein“ u. Ä. werden Organisation
  (`vereinsportal/namen.py`). Fehler korrigiert man im Adressbuch.
- **Einwilligung zur E-Mail:** Steht ein Spender in der Liste „Spender mit E-Mail“ und nicht auf
  „immer per Post“, gilt das als Einwilligung ab dem Tag des Einlesens. Eine im Adressbuch schon
  eingetragene andere E-Mail wird nicht überschrieben.
- **Nichts wird gelöscht:** Früher hochgeladene Sammelbescheinigungen bleiben in ihrer Tabelle,
  werden aber nicht mehr verwendet.

## Nachtrag: Spalten zum Versand im Finanzexport

Die Spalten „Versendet am“, „SQ-verschickt“ und „SQ-erstellt Datum“ stehen nur in der Übersicht
des Finanzexports, wenn sie beim Erstellen unter „Erweiterte Einstellungen → Spalten“ angekreuzt
sind; anfangs sind sie es nicht. Ohne sie wusste bintafeln (wie zuvor das alte Programm) nicht,
was im Vereinsportal schon versendet ist. Deshalb:

- Der Dienst `abruf` (ADR 0127) kreuzt die drei Spalten vor „Erstellen“ an und lässt alle
  anderen Häkchen, wie sie sind. Einen schon vorhandenen Export desselben Zeitraums ohne diese
  Spalten benutzt er nicht, sondern erzeugt ihn neu.
- Als versendet gilt eine Spende, wenn „Versendet am“ oder „SQ-erstellt Datum“ ausgefüllt ist
  oder „SQ-verschickt“ nicht „Nein“ (bzw. leer, 0, falsch) ist.
- Fehlen die Spalten in einer hochgeladenen Datei, meldet das Einlesen das ausdrücklich mit dem
  Weg dorthin, statt „0 versendet“ zu sagen.

## Nachtrag: Einzelspenden bestätigt bintafeln selbst

Bisher war ein einzelner, im Vereinsportal noch nicht versendeter Beleg selbst die Bestätigung
(er lag dem Dankesbrief bei). Seit die Bestätigung aus bintafeln genauso aussieht wie die aus dem
Vereinsportal (ADR 0136), stellt bintafeln auch dafür die Bestätigung aus: Alles, was im
Vereinsportal nicht versendet ist, bestätigt bintafeln – eine Spende einzeln, mehrere im Jahr als
Sammelbestätigung. Der Beleg aus dem Vereinsportal liegt dann nicht bei und sollte dort nicht mehr
verschickt werden. Die Seite „Zuwendungsbestätigungen“ zeigt dazu alle Spender des Jahres mit dem
Stand ihrer Bescheinigung (`bestaetigung.spenderuebersicht()`).
