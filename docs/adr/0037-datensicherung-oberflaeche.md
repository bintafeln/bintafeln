# 0037: Datenexport und Zurücklesen in der Oberfläche

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die Server-Sicherung (ADR 0008) läuft automatisch, ist aber an den Server und dessen Schlüssel
gebunden. Die Tafel möchte zusätzlich sämtliche Daten selbst als Datei sichern, extern aufbewahren
und wieder einlesen können – vollständig oder in Teilen, wobei ein Teil nur aktualisieren und
nichts anderes löschen darf.

## Entscheidung

- Export aller Daten oder einzelner Bereiche als eine Datei: Django-Serialisierung (JSON) der
  eigenen Modelle samt hochgeladener Dateien (intern verschlüsselte werden entschlüsselt),
  gzip, dann Fernet-Verschlüsselung mit einem Schlüssel aus einem selbst gewählten Passwort
  (PBKDF2-SHA256, 480 000 Durchläufe, zufälliges Salz).
- Zurücklesen immer mit Vorschau. „Aktualisieren“ schreibt Datensätze mit ihrem Schlüssel
  (neu oder überschreiben) und löscht nie. „Vollständig ersetzen“ nur mit vollständiger Datei,
  frischer Server-Sicherung und ausdrücklicher Bestätigung. Alles in einer Transaktion;
  fehlende Verweise führen zu einer verständlichen Meldung ohne Änderung.
- Dateien aus neueren Versionen (Migrationsstand) werden abgelehnt; ältere sind erlaubt.
- Eine Kennung je Installation (`TafelEinstellungen.installation`) warnt beim Einlesen fremder
  Dateien.
- Rechte `daten.exportieren` und `daten.importieren`, Vorgabe nur Admin.

## Begründung

Das eingebaute Serialisierungsformat folgt den Modellen automatisch und bleibt mit späteren
Migrationen lesbar. Die Datei ist mit dem Passwort unabhängig vom Server-Schlüssel, damit sie
auch auf einem neuen Server zurückgelesen werden kann. Für sehr große Bestände bleibt die
Server-Sicherung der Weg; der Export hält alles im Arbeitsspeicher.
