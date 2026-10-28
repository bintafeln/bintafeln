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
- Zeitraum immer der ganze Monat bzw. dieser und der nächste, wie der Plan auf Papier; am
  Monatsende ist so schon der nächste Plan zu sehen. (Zuerst ab heute; vergangene Tage im Plan
  zu sehen war den Tafeln aber wichtiger; später doch lieber ohne: vergangene Tage fallen auf dem
  Monitor immer weg, der Monat beginnt also mit heute.) Alternativ je Seite „die nächsten N Wochen ab heute“
  (`AushangSeite.wochen`, 1–26, Vorgabe 9) ohne vergangene Tage; der Fahrerplan kommt dann als
  eine Folie statt je Monat. Vorhandene Fahrerplan-Seiten wurden auf 9 Wochen umgestellt.
- Der Monitor (`/aushang/zeigen/<schluessel>/`) braucht keine Anmeldung, wie die Geräte des
  Aufrufs (ADR 0050). Er zeigt nur Namen, nie Telefon, E-Mail oder Anmerkungen. „Neuen Link
  erzeugen“ und „Aktiv“ aus sperren ihn; fragt der Monitor selbst nach (`X-Aushang`), antwortet
  der Server dann mit 204 und der Monitor leert sich.
- `static/js/aushang.js` wechselt die Folien, sucht je Folie die größte Schrift, bei der alles
  ohne Scrollen passt, holt jede Minute den neuen Stand und lädt alle sechs Stunden die ganze
  Seite neu (neue Programmversion). Vollbild per Knopf oder Browser mit `--kiosk`.

- Antippen zeigt eine Seite groß, immer ganz eingepasst (Schieben war am Touch-Monitor nicht
  brauchbar); oben steht je Seite ein deutlicher Knopf (`kurz` aus `folien()`, z. B. „Fahrer
  Oktober“), „Übersicht“ oder 30 Sekunden ohne Eingabe führen zurück. Dort steht ein QR-Code mit dem Link zur Seite im
  Programm (Ändern am eigenen Handy mit Anmeldung; je Aushang abschaltbar).
- Ändern am Monitor (je Aushang abschaltbar) nur mit **persönlicher PIN** (`MonitorPin`, mindestens
  6 Ziffern, gehasht wie ein Passwort, selbst festgelegt unter „Mein Konto → PIN für Aushang-Monitore“ über den Hook
  `Modul.mein_konto`, nach 5 Fehlversuchen 15 Minuten gesperrt). Man tippt auf einen Platz, wählt seinen
  Namen und gibt die PIN ein; `Aushangseite.platz()` liefert den Dialog, `Aushangseite.aendern()`
  prüft, was die bestätigte Person darf: sich selbst austragen, selbst auf einem freien Platz
  einspringen, mit dem Planungsrecht des Moduls alles (Ersatz, Gast, zurücknehmen). Eingetragen
  wird „<Konto> am Monitor …“, das Änderungsprotokoll nennt die Person (`set_actor`).
  Vergangene Tage sind am Monitor nicht änderbar.

## Begründung

Ein eigenes Modul mit Hook hält Dienstplan und Fahrdienst unabhängig voneinander und lässt
später weitere Seiten zu (z. B. Wochenübersicht). Der Schlüssel im Link hat sich beim Aufruf
bewährt; Geräte am Monitor müssen sich so nicht anmelden und keine Zwei-Faktor-Sitzung halten.
Das Einpassen per Schriftgröße statt Skalieren hält die Tabellen scharf und nutzt die Breite.
Eine gemeinsame PIN je Monitor hätte nicht gezeigt, wer etwas geändert hat; eine Anmeldung mit
Passwort und Zwei-Faktor-Code am Monitor wäre umständlich und ließe Sitzungen offen. Die
persönliche PIN reicht für das, was am Monitor geht (Dienste eines Tages), und das
Änderungsprotokoll bleibt aussagekräftig. Wer mehr ändern will, nutzt den QR-Code und das Handy.
