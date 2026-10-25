# 0041: https im Heimnetz für die Kamera

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die Kamera als Barcode-Scanner (ADR 0029) geben Browser nur auf sicheren Seiten frei (https oder
`localhost`). Im Entwicklungsmodus läuft bintafeln über `http://IP`, beim Testen im Heimnetz
fragt das Handy deshalb gar nicht erst nach der Kamera. Eine Webseite kann das nicht umgehen.
Wer die Kamera früher abgelehnt hat, wird vom Browser ebenfalls nicht mehr gefragt.

## Entscheidung

- Neue optionale Variable `BINTAFELN_HEIMNETZ_ADRESSE` (nur Entwicklungsmodus). Ist sie gesetzt,
  liefert Caddy diese Adresse zusätzlich über https mit einem selbst ausgestellten Zertifikat aus
  (`tls internal`, `default_sni`, weil Geräte eine IP ohne Namen aufrufen). Ein eigener
  http-Block für die Adresse verhindert die Umleitung, `http://IP` geht weiter.
- Über http zeigt der Einlass statt einer Fehlermeldung den Knopf „Über https öffnen“, wenn die
  Variable gesetzt ist, sonst eine Erklärung für Mitarbeitende und Admin.
- Vor der Abfrage kündigt bintafeln sie an. Ist die Kamera gesperrt (Permissions-API oder
  Ablehnung), zeigt es Schritte zum Freigeben passend zu Android, iPhone oder PC und einen Knopf
  „Erneut versuchen“; ebenso, wenn eine andere App die Kamera belegt. Kennt ein Gerät keine
  Rückkamera, wird jede Kamera genommen.

## Begründung

Ein selbst ausgestelltes Zertifikat ist für Tests im eigenen Netz ausreichend und braucht weder
Domain noch Internetzugang; die Warnung im Browser bestätigt man einmal je Gerät. Der normale
http-Zugang bleibt, damit sich am bisherigen Testen nichts ändert. Im Produktivbetrieb gilt
weiter das echte Zertifikat über `BINTAFELN_DOMAIN`.
