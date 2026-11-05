"""Fernsicherung (ADR 0106): Die in der Oberfläche eingestellte, verschlüsselt gespeicherte
rclone-Konfiguration für den Dienst „backup“ entschlüsselt als Datei bereitstellen.

Der Dienst „backup“ ist kein Django und kann das Geheimnis (Fernet) nicht selbst entschlüsseln;
darum schreibt der Dienst „app“ die entschlüsselte ``rclone.conf`` in ein nur intern geteiltes
Verzeichnis (Volume), das „backup“ nur lesen darf. Aufgerufen beim Start (entrypoint) und nach
jedem Speichern in der Oberfläche.
"""

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# In der Entwicklung/Tests ohne das Volume: ein Ort, der keinen Fehler wirft.
KONFIG_PFAD = Path(os.environ.get("BINTAFELN_FERNSICHERUNG_PFAD", "/app/data/fernsicherung"))


def schreiben() -> bool:
    """Schreibt die rclone.conf (oder entfernt sie, wenn nichts eingestellt ist).

    Liefert True, wenn eine Konfiguration geschrieben wurde. Fehler (Volume fehlt, keine Rechte)
    werden verschluckt – ohne Fernablage soll nichts abbrechen."""
    from apps.core.models import Fernsicherung

    obj = Fernsicherung.laden()
    text = obj.konfig
    datei = KONFIG_PFAD / "rclone.conf"
    schluessel_datei = KONFIG_PFAD / "sftp_key"
    try:
        KONFIG_PFAD.mkdir(parents=True, exist_ok=True)
        # Optionale SFTP-Schlüsseldatei; die Konfig verweist mit key_file darauf
        if obj.schluessel.strip():
            schluessel_datei.write_text(obj.schluessel.rstrip("\n") + "\n")
            schluessel_datei.chmod(0o600)
        else:
            schluessel_datei.unlink(missing_ok=True)
        if (text or "").strip():
            datei.write_text(text if text.endswith("\n") else text + "\n")
            datei.chmod(0o600)
            return True
        datei.unlink(missing_ok=True)
    except OSError as fehler:
        # Ohne Fernablage soll nichts abbrechen; trotzdem protokollieren, damit ein echtes
        # Rechte-/Volume-Problem nicht lautlos verschwindet (z. B. Verzeichnis gehört root).
        log.warning("Fernsicherungs-Konfig konnte nicht nach %s geschrieben werden: %s",
                    datei, fehler)  # fmt: skip
    return False
