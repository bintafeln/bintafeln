# ADR 0106: Sicherung außer Haus über rclone (Fernablage)

## Problem

Der Dienst „backup“ (ADR 0042) sichert verschlüsselt in den Sicherungsordner des Servers oder in
einen Ordner unter `/media`/`/mnt` (USB-Platte, eingehängtes Netzlaufwerk). Eine Sicherung, die nur
auf demselben Server oder im selben Raum liegt, schützt nicht vor Server-Defekt, Diebstahl oder
Brand (3-2-1-Regel: eine Kopie außer Haus). Tafeln möchten automatisch auf einen fremden Speicher
sichern – SFTP, FTP, S3-kompatibel (Backblaze/Wasabi/Hetzner), WebDAV/Nextcloud u. a.

## Entscheidung

Der Dienst „backup“ kann Sicherungen zusätzlich auf eine **Fernablage** hochladen, umgesetzt mit
**rclone** (deckt viele Anbieter mit einem Werkzeug ab).

- Das Image `docker/backup` enthält `rclone`.
- In der Oberfläche („Einstellungen → Sicherungen → Sicherung außer Haus“) fügt die Tafel einen
  fertigen rclone-Remote-Block ein (`FernsicherungForm`). Er wird **verschlüsselt** gespeichert
  (`Fernsicherung.konfig_verschluesselt` über `apps.core.geheimnis`, ADR 0016) und aus
  Sicherheitsgründen nie wieder angezeigt (leer lassen = unverändert, Häkchen zum Entfernen).
- Weil der Dienst „backup“ kein Django ist und das Geheimnis (Fernet) nicht entschlüsseln kann,
  schreibt der Dienst „app“ die entschlüsselte `rclone.conf` in ein nur intern geteiltes Volume
  (`fernsicherung`, in „app“ beschreibbar, in „backup“ nur lesbar). Das geschieht beim Start
  (`manage.py fernsicherung_schreiben` im entrypoint) und nach jedem Speichern
  (`apps.core.fernsicherung.schreiben`).
- Ein Sicherungsauftrag kann als `ziel` eine eingerichtete Fernablage haben (z. B. `fern:bintafeln`).
  Der Dienst erzeugt die (bereits verschlüsselte) Sicherung lokal in einem Zwischenordner, lädt sie
  mit `rclone copy` hoch und wendet die Aufbewahrung (Anzahl/Tage) auch dort an
  (`rclone lsf`/`purge`).

## Begründung

- rclone ist etabliert, ein einzelnes Binary und deckt SFTP, FTP(S), S3, WebDAV/Nextcloud, Storage
  Boxes u. v. m. ab – eine Integration für alle Fälle, einstellbar je Auftrag in der Oberfläche.
- Die Sicherungen sind schon mit age verschlüsselt; der Fremdspeicher sieht nur Datensalat, der
  private Schlüssel bleibt wie bisher getrennt. So ist „außer Haus“ auch bei einem wenig
  vertrauenswürdigen Anbieter unbedenklich.
- Geheimnisse bleiben verschlüsselt in der Datenbank (ADR 0016); die entschlüsselte Konfig erreicht
  den Nicht-Django-Dienst nur über ein privates Volume, nicht über die Datenbank im Klartext –
  genauso wie der age-Schlüssel dem Dienst als Datei/Variable zugeht, nicht über die Datenbank.
- Kein zusätzliches Programm bei der Tafel nötig: Ziel kann ein günstiger Speicher, der eigene kleine
  Server (per SSH/SFTP) oder eine Cloud sein.
