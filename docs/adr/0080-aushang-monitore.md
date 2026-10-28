# 0080: Aushang-Monitore

- Status: Angenommen
- Datum: 2026-10-28

## Problem

Die Tafeln möchten den Dienstplan der Ausgabestellen und den Fahrerplan auf Monitoren aushängen,
z. B. im Fahrerraum. Die Seiten im Programm haben Menü, Kopfzeile und Knöpfe, brauchen eine
Anmeldung und passen nicht auf einen Bildschirm. Mehrere Pläne sollen auf einem Monitor
zusammengefasst werden können, eingerichtet direkt im Programm.

## Entscheidung

- Neues zuschaltbares Modul `aushang` (ADR 0049) mit `Aushang` (ein Monitor: Name, aktiv, geheimer
  Schlüssel, Seiten gleichzeitig 1 oder 2, Sekunden je Seite) und `AushangSeite` (Seitenart,
  Auswahl, Zeitraum 1 oder 2 Monate, Reihenfolge). Einstellungen unter „Einstellungen →
  Dienstpläne → Aushang-Monitore“, Recht `aushang.einrichten` (Vorgabe Büro).
- Die Seitenarten kommen von den Modulen über den neuen Hook `Modul.aushang` (`Aushangseite`:
  Kennung, Titel, Recht, `auswahl()`, `folien(wert, von, bis)`). Dienstplan: je Ausgabetag einer
  Stelle eine Folie; Fahrdienst: je Monat eine Folie. Beide nutzen dieselbe Tabelle wie die Seite
  im Programm (`_tabelle.html`). Seiten ausgeschalteter Module fallen still weg.
- Zeitraum immer ab heute bis zum Ende dieses bzw. des nächsten Monats: vergangene Tage braucht
  am Monitor niemand, am Monatsende ist so schon der nächste Plan zu sehen.
- Der Monitor (`/aushang/zeigen/<schluessel>/`) braucht keine Anmeldung, wie die Geräte des
  Aufrufs (ADR 0050). Er zeigt nur Namen, nie Telefon, E-Mail oder Anmerkungen. „Neuen Link
  erzeugen“ und „Aktiv“ aus sperren ihn; fragt der Monitor selbst nach (`X-Aushang`), antwortet
  der Server dann mit 204 und der Monitor leert sich.
- `static/js/aushang.js` wechselt die Folien, sucht je Folie die größte Schrift, bei der alles
  ohne Scrollen passt, holt jede Minute den neuen Stand und lädt alle sechs Stunden die ganze
  Seite neu (neue Programmversion). Vollbild per Knopf oder Browser mit `--kiosk`.

## Begründung

Ein eigenes Modul mit Hook hält Dienstplan und Fahrdienst unabhängig voneinander und lässt
später weitere Seiten zu (z. B. Wochenübersicht). Der Schlüssel im Link hat sich beim Aufruf
bewährt; Geräte am Monitor müssen sich so nicht anmelden und keine Zwei-Faktor-Sitzung halten.
Das Einpassen per Schriftgröße statt Skalieren hält die Tabellen scharf und nutzt die Breite.
