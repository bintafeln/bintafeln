# 0095 – Produktivstart: Testdaten löschen beim Umstieg auf Echtdaten

## Problem

Während eine Tafel bintafeln einrichtet und ausprobiert, entstehen Test- und Phantasiedaten:
erfundene Haushalte, Abholungen, Anträge, Spenden, Mitglieder, Konten. Spielt die Tafel später die
echten Daten ein, soll sie mit einem sauberen Stand starten – also alle Testdaten los sein, ohne
die bereits erledigte Einrichtung (Ausgabestellen, Kundengruppen, Rollen, Einstellungen, Vorlagen)
neu machen zu müssen. Der Kundenstamm-Import tauscht nur die Haushalte aus; Abholungen, Statistik,
Konten und Co. hängen an der Kundennummer bzw. am Konto und bleiben sonst erhalten.

## Entscheidung

- Eine eigene Admin-Funktion **Produktivstart** (`apps/core/produktivstart.py`, Ansichten in
  `views_produktivstart.py`, unter „Einstellungen → Systemsteuerung“) löscht einmalig die
  **Bewegungs- und Testdaten der ausgewählten Bereiche** und lässt die **Einrichtung** stehen.
- Der Admin **wählt je Bereich** (`GRUPPEN`), was gelöscht wird (Vorgabe: alle angehakt): Kunden
  und Ausgabe, Anträge und Warteliste, Spenden/Mitglieder/Adressbuch, Modul-Bewegungsdaten,
  Änderungsprotokoll, andere Konten mit Personal. Je Bereich zeigt die Seite die Zahl der
  Datensätze.
- **Gelöscht** wird je Bereich eine fest umrissene Liste von Modellen: Haushalte und alles daran
  (Personen, Abholer, Sperren, Bemerkungen, Notizen, Nachrichten, Dokumente, Historie, Abholungen,
  Ausnahmen, Zugriffe, Importläufe), Kundenkonto-Buchungen, Sonderaktionen/Teilnahmen,
  Korrekturwünsche, Anträge und Warteliste, Adressen/Spenden/Mitglieder, Serienbrief-Versände, das
  Änderungsprotokoll (auditlog) und die Bewegungsdaten der Module (Aufruf-Handyzugänge,
  Wochenübersicht-Selbstabholer, Abrechnungen, Fahrdienst-/Dienstplan-Ausfälle, Tickets).
  **Personal** (Verträge, Abwesenheiten, Stunden, Schulungen, Dokumente, Stammdaten) wird
  ebenfalls gelöscht.
- **Erhalten** bleibt alles, was in keiner gewählten Gruppe aufgeführt ist – damit ein vergessenes
  Einrichtungs-Modell nie versehentlich gelöscht wird (Vorgabe: behalten). Das sind: alle
  Einstellungen und Listen (Tafel, Mail, Ausgabe, Antrag …), Ausgabestellen mit Zeiten und
  Kontakten, Kundengruppen mit Zeiten, Einkommensarten, alle Vorlagen (Ausweis, Serienbrief,
  Notiz, Dokumentarten, Antragstexte), Adresskategorien, Modul-Einstellungen und -Vorlagen,
  Rollen und Rechte.
- **Konten:** Ist der Bereich „Andere Konten und Personal“ gewählt, bleibt nur das auslösende
  Admin-Konto; alle anderen Konten werden mit ihren Personaldaten gelöscht. Das ist eine bewusste
  Ausnahme von ADR 0015 („Mitarbeitende nie löschen, nur sperren“), weil es beim Produktivstart
  reine Testkonten sind. Im Alltag gilt ADR 0015 weiter.
- **Sicherheit:** Die Oberfläche erzeugt vorher **automatisch eine verschlüsselte
  Komplett-Sicherung** (dieselbe wie die Datensicherung, ADR 0037) und gibt sie zum Download;
  schlägt die Sicherung fehl, wird nichts gelöscht. Zusätzlich braucht es eine Tippbestätigung
  („PRODUKTIVSTART“). Neues Recht `system.produktivstart` (nur der Admin hat es), im Demo-Betrieb
  gesperrt (`@nicht_in_demo`). Das Löschen läuft in einer Transaktion ohne Auditlog; gegenseitige
  Fremdschlüssel löst ein Mehrfach-Durchlauf auf.

## Begründung

Default-behalten (feste Löschliste statt „alles außer einer Behalten-Liste“) ist die sichere
Richtung: Vergisst man ein Modell, bleibt es erhalten statt unwiederbringlich weg zu sein. Die
automatische Sicherung vorher entspricht der Grundregel „keine Löschung ohne vorherige Sicherung“.
Die Statistik muss nicht eigens geleert werden, weil sie aus den gelöschten Abholungen gerechnet
wird.
