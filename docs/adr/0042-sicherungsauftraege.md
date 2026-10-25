# 0042: Sicherungsaufträge in der Oberfläche

- Status: Angenommen
- Datum: 2026-10-25

## Problem

Die Sicherung lief einmal täglich in einen Ordner; Uhrzeit und Anzahl standen in `.env`. Tafeln
ohne IT-Kenntnisse wollen selbst sofort sichern, regelmäßig zusätzlich auf ein externes Medium
(USB-Platte, NAS) sichern und festlegen, wie viele Stände bzw. wie viele Tage aufbewahrt werden,
ohne die Kommandozeile zu benutzen.

## Entscheidung

- Neue Tabelle `SicherungsAuftrag` (Name, Ziel, Wochentage, Uhrzeit, Aufbewahrung nach Anzahl
  und/oder Tagen, aktiv) und Seite „Einstellungen → Sicherungen“ mit „Jetzt sichern“ je Auftrag.
- Die Oberfläche führt nichts selbst aus. Der Dienst `backup` liest die Aufträge alle
  15 Sekunden mit `psql` aus der Datenbank, führt fällige oder angeforderte aus und schreibt
  Lebenszeichen (`SicherungsDienst`), sichtbare Ziele, Ergebnis, Stände und freien Platz zurück.
  Werte gehen nur über psql-Variablen in SQL.
- Ziele: der Sicherungsordner oder Ordner unter `/media` und `/mnt`, die in den Dienst
  eingebunden sind. Später eingehängte Medien sieht ein Container erst nach einem Neustart; der
  Dienst beendet sich deshalb alle 30 Minuten, wenn er nichts zu tun hat, und Docker startet ihn
  neu. `rslave` hätte das ohne Neustart gelöst, verhindert aber auf Servern ohne geteilte Mounts
  (z. B. manche VMs, LXC) den Start des ganzen Aufbaus. Gesichert wird
  in einen Unterordner `bintafeln`. Je Ziel ein Auftrag, damit sich die Aufbewahrung zweier
  Aufträge nicht gegenseitig löscht. Die neueste Sicherung bleibt immer erhalten.
- Ein Standard-Auftrag für den Sicherungsordner entsteht per Migration aus den bisherigen
  `.env`-Werten, ist ausschaltbar, aber nicht löschbar; `./betrieb sichern` und das Update
  nutzen ihn.
- Nur mit dem neuen Recht `system.sicherung` (Vorgabe Admin); in der Demo gesperrt.

## Begründung

Die Weboberfläche bekommt keine weiteren Rechte auf dem Server; sie schreibt nur Daten, die der
ohnehin vorhandene Dienst ausführt. Verschlüsselung, Dateiaufbau und Wiederherstellung bleiben
unverändert. `/media` und `/mnt` sind die üblichen Orte für eingehängte Medien unter Debian.
