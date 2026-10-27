# 0073: Papierkorb für gelöschte Daten

- Status: Angenommen
- Datum: 2026-10-27

## Problem

Ein falscher Klick auf „Löschen“ war bisher endgültig: ein Haushalt mit Personen, Notizen,
Dokumenten und Historie, eine Adresse, eine Ausgabestelle oder eine Rolle. Zurück ging es nur
über eine Datensicherung, und die setzt mehr zurück als den einen Fehler. Nur Anträge hatten
einen eigenen Papierkorb (ADR 0024).

## Entscheidung

- Löschen in der Oberfläche läuft über `apps.core.papierkorb.loeschen()`. Es sammelt mit
  Djangos `Collector` alles ein, was beim Löschen mitgehen würde (Kaskade), dazu, was nur über
  die Kundennummer am Haushalt hängt (Notizen, Historie, Teilnahmen, Dokumente). Davon legt es
  eine Kopie (Django-Serialisierung) als `PapierkorbEintrag` ab und löscht dann. Felder anderer
  Datensätze, die beim Löschen geleert werden (`SET_NULL`, z. B. Kontobuchungen), merkt es sich.
- `wiederherstellen()` legt alles mit denselben Nummern wieder an und setzt die gemerkten
  Verweise zurück. Gibt es einen Datensatz schon wieder (z. B. Kundennummer durch einen Import
  neu vergeben) oder fehlt etwas, worauf verwiesen wird (z. B. die Kundengruppe), wird nichts
  geändert und es gibt eine verständliche Meldung. Die Fremdschlüssel prüft PostgreSQL dafür
  vor dem Ende der Transaktion (`SET CONSTRAINTS ALL IMMEDIATE`).
- Verschlüsselte Dateien (`privatdateien`) bleiben liegen, bis der Eintrag endgültig gelöscht
  wird. Modelle nennen ihre Datei in `PRIVATDATEI = (ordner, feld)`.
- Sehen und wiederherstellen darf ein Eintrag, wer das Recht hat, mit dem gelöscht wurde
  (`PapierkorbEintrag.recht`). Bei Kundendaten gilt zusätzlich die Zuordnung zu Ausgabestellen
  (ADR 0034) über die Ausgabestelle beim Löschen. Eine Rolle stellt nur wieder her, wer alle
  ihre Rechte hat. Ein neues Recht braucht es nicht; der Menüpunkt erscheint, sobald es etwas zu
  sehen gibt.
- `TafelEinstellungen.papierkorb_tage` (30, 60, 90 oder 365 Tage, Vorgabe 30): danach löscht
  `fristen_anwenden()` endgültig (beim Aufruf der Startseite wie die übrigen Fristen).
  „Endgültig löschen“ geht auch sofort.
- Nicht über den Papierkorb: Löschfristen, der Import (Vollaustausch), Abholungen beim
  Bearbeiten (die Rücknahme bucht das Konto zurück), Anträge (eigener Papierkorb), Mitarbeitende
  (werden nur gesperrt, ADR 0015) und technische Einträge wie Sicherungsaufträge.
- Die Einträge stehen nicht im Änderungsprotokoll (django-auditlog): Das Löschen und
  Wiederherstellen der Daten selbst steht dort schon, und eine Kopie aller Inhalte im Protokoll
  bliebe nach dem Leeren übrig. Die Auskunft zum Haushalt nennt, was zu ihm noch im Papierkorb
  liegt.

## Begründung

Eine zentrale Funktion statt eines „gelöscht“-Felds in jedem Modell: Kein Modell und keine
Abfrage muss gelöschte Datensätze ausblenden, Eindeutigkeiten (Kundennummer) bleiben einfach,
und neue Modelle sind ohne Zutun dabei. Die Kopie im Format der Datensicherung ist dieselbe
Technik wie ADR 0037. Die Frist hält die Datensparsamkeit ein: Gelöschtes bleibt nur kurz
wiederherstellbar.
