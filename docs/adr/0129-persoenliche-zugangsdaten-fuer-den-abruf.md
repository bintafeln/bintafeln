# ADR 0129: Persönliche Zugangsdaten für den Abruf, Historie der Abrufe

## Problem

Für den automatischen Abruf (ADR 0127) stand eine Anmeldung im Vereinsportal in den Einstellungen
des Moduls. Jeder mit dem Recht des Moduls rief damit ab – mit dem Konto und der
Zwei-Faktor-Anmeldung einer einzelnen Person. Eine Anmeldung im Vereinsportal ist aber persönlich:
Niemand soll mit dem Konto einer anderen Person abrufen, und niemand soll die eigene Anmeldung
abgeben müssen. Außerdem war auf der Seite nicht zu sehen, welche Zeiträume schon abgerufen sind.

## Entscheidung

- **Zugangsdaten je Konto:** `Zugang` (E-Mail, Passwort verschlüsselt nach ADR 0016) gehört zu
  genau einem bintafeln-Konto. Eingetragen, geändert und gelöscht wird er nur auf der eigenen
  Seite „Meine Zugangsdaten“; es gibt keine Ansicht, die fremde Zugänge zeigt – auch nicht für
  den Admin. `abruf.starten()` nimmt immer den Zugang der Person, die startet.
- **2FA-Code nur von der Person, die gestartet hat:** Der laufende Abruf merkt sich, wem er
  gehört (`Abruf.benutzer`). Andere sehen, wer abruft, bekommen aber kein Feld für den Code;
  `abruf.code_senden()` lehnt sie ab. Abbrechen dürfen alle mit dem Recht, damit ein hängender
  Abruf niemanden blockiert.
- **Eigenes Recht:** `vereinsportal.abruf` („Automatischer Abruf mit eigenen Zugangsdaten“),
  getrennt vom Einlesen von Hand. Keine mitgelieferte Rolle bekommt es; der Admin hat es immer,
  die Tafel gibt es z. B. einer Rolle für den Vorstand.
- **Historie:** Jeder Abruf ist ein `Abruf` (wer, wann, Zeitraum, Stand, Zahlen des Einlesens,
  Meldung bei Fehlern). Die Abruf-Seite zeigt eine Kurzübersicht und die letzten Abrufe.
- **Ergebnis für alle:** Was ein Abruf einliest, liegt im gemeinsamen Spendenpool (ADR 0128).
- Die Adressen der Seiten im Vereinsportal bleiben gemeinsame Einstellungen der Tafel.

## Übernahme der bisherigen Zugangsdaten

Die Migration gibt die gemeinsamen Zugangsdaten dem einen aktiven Konto, dessen E-Mail der
Anmeldung im Vereinsportal entspricht. Gibt es kein oder mehr als ein solches Konto, entfallen
sie und werden neu eingetragen: Lieber einmal neu tippen, als dass jemand die Anmeldung einer
anderen Person erbt. Verloren geht dabei nichts, was die Person nicht kennt.

## Begründung

- Wer im Vereinsportal etwas tut, tut es unter dem eigenen Namen – mit gemeinsamen Zugangsdaten
  wäre das nicht mehr nachvollziehbar.
- Gelöscht wird ein Zugang endgültig, nicht in den Papierkorb (ADR 0073): Ein Geheimnis soll
  niemand wiederherstellen können.
- Zugang und eigene Abrufe stehen in der Auskunft nach Art. 15 zum Konto (ohne Passwort). Die
  Historie nennt nur, wer wann welchen Zeitraum abgerufen hat.
- Der Dienst `abruf` bekommt die Zugangsdaten wie bisher nur für die Dauer eines Abrufs.
