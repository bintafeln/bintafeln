# 0076: Einstellungen ohne Speichern-Knopf

- Status: Angenommen
- Datum: 2026-10-27

## Problem

Wer auf einer Einstellungsseite etwas ändert und den Knopf „Speichern“ unten auf der Seite
vergisst, verliert die Änderung, ohne es zu merken.

## Entscheidung

- Formulare mit `data-autosave` speichern jede Änderung sofort (`static/js/autosave.js`):
  Häkchen, Auswahl und Dateien gleich, Text- und Zahlfelder 1,2 Sekunden nach dem Tippen, spätestens
  beim Verlassen des Feldes oder der Seite. Der Speichern-Knopf wird ausgeblendet.
- Das Skript schickt das ganze Formular wie bisher an dieselbe Ansicht. Leitet sie weiter, war es
  erfolgreich („✓ gespeichert“ am Feld). Sonst liest es die Fehler aus der zurückgegebenen Seite
  und zeigt sie am Feld; gespeichert bleibt der alte Wert. Die Ansichten bleiben unverändert.
- Eingeschaltet auf allen Einstellungsseiten (Tafel, E-Mail, Speicher, Kundenstamm, Ausgabe,
  Anträge, Personal, Anmeldung, Mitglieder, Spenden und die Module Aufruf, Abrechnung,
  Fahrdienst, Warteliste). Neue Einstellungsseiten setzen `data-autosave` am Formular.
- Löschen fragt weiter nach. Knöpfe mit eigener Aktion (Verbindung prüfen, Testmail, Beispiel
  anlegen) stehen in eigenen Formularen und bleiben Knöpfe.

## Begründung

Ein Skript für alle Seiten statt einer Änderung an jeder Ansicht: Prüfung, Protokoll und Rechte
laufen unverändert über den bestehenden Weg. Ohne JavaScript funktioniert alles wie bisher.
