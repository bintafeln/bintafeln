# ADR 0126: Spendenbelege aus dem Vereinsportal

## Problem

Manche Tafeln stellen ihre Spendenbescheinigungen aus rechtlichen Gründen weiterhin im
Vereinsportal aus und versenden sie dort. Das Vereinsportal kann Mehrfachspendern die
Bescheinigung aber nicht per E-Mail schicken. Bisher half dabei ein eigenes kleines Programm
neben bintafeln: Es holt Finanzexport und Spenderliste aus dem Vereinsportal, liest die
Spendenbelege und sortiert die Spender. Die Spenden in bintafeln (ADR 0055, 0056) sind dafür
kein Ersatz, weil sie eigene Zuwendungsbestätigungen ausstellen.

## Entscheidung

Ein zuschaltbares Modul `vereinsportal` übernimmt die Regeln des bisherigen Programms
unverändert, in drei Schritten:

1. **Einlesen und Auswerten (dieser Schritt):** Finanzexport (ZIP) und Liste „Spender mit
   E-Mail“ (Excel) werden hochgeladen. `einlesen.py` liest die Belege (Belegnummer aus dem
   Dateinamen, Spender aus der Zeile unter der Absenderzeile, „bereits versendet“ aus dem Blatt
   „Spenden - Übersicht“), `auswertung.py` bildet die Gruppen Einfach-/Mehrfachspender mit und
   ohne E-Mail.
2. **Versand an Mehrfachspender:** hochgeladene Sammelbescheinigung je Spender, per E-Mail über
   `apps.core.mail` oder als Druck-PDF.
3. **Automatischer Abruf:** ein eigener, optionaler Dienst mit Browser holt die Dateien nach
   Eingabe des 2FA-Codes; bintafeln selbst bekommt keinen Browser.

Die Belege liegen in eigenen Modellen (`Beleg`, `Kontakt`), nicht als `Spende` und nicht im
Adressbuch.

## Begründung

- **Getrennt von den Spenden in bintafeln:** Würden die Belege als `Spende` angelegt, könnte
  bintafeln dafür eine zweite Zuwendungsbestätigung ausstellen. Für eine Spende darf es nur eine
  geben; die des Vereinsportals gilt.
- **Kein Produktname, keine festen Werte:** Vereinsnummer, Listen und der Name im Absender
  gehören in die Einstellungen der Tafel; die Oberfläche spricht neutral vom „Vereinsportal“.
- **Erst der Weg von Hand:** Der Abruf mit Browser hängt an den Seiten des Vereinsportals und
  kann jederzeit brechen. Das Hochladen bleibt deshalb dauerhaft als zweiter Weg.
- **Datensparsam:** Die Belege sind Kopien; die Originale bleiben im Vereinsportal. Sie werden
  verschlüsselt gespeichert (`privatdateien`) und nach der eingestellten Zeit gelöscht
  (Vorgabe 2 Jahre). Die Spenderliste wird bei jedem Einlesen vollständig ersetzt.
