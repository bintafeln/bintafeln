"""gunicorn-Einstellungen für den Webserver (ADR 0111).

Die Werte lassen sich über die ``.env`` an die Servergröße anpassen, ohne das Abbild neu zu bauen.
Vorgaben sind bewusst sparsam gewählt, weil bintafeln je Tafel auf einem kleinen VPS läuft:

- ``BINTAFELN_WORKER``        Anzahl der Arbeitsprozesse (Vorgabe 3). Jeder Worker belegt eigenen
                              Arbeitsspeicher; auf einem 2-GB-Server sind 2 oft ruhiger.
- ``BINTAFELN_TIMEOUT``       Sekunden, nach denen ein hängender Worker beendet und neu gestartet
                              wird (Vorgabe 120). Große Importe/PDFs, die im Aufruf selbst laufen,
                              brauchen bei sehr langsamen Servern evtl. mehr.
- ``BINTAFELN_MAX_REQUESTS``  Nach so vielen Anfragen wird ein Worker neu gestartet (Vorgabe 1000).
                              Das gibt langsam anwachsenden Speicher zuverlässig wieder frei
                              (z. B. nach vielen Bild-/PDF-Aufrufen). 0 schaltet das Recycling ab.

Diese Datei wird von gunicorn selbst gelesen (``--config``), nicht von Django; daher nur
``os.environ`` statt der Django-Einstellungen.
"""

import os


def _zahl(name: str, standard: int) -> int:
    wert = os.environ.get(name, "").strip()
    if not wert:
        return standard
    try:
        return max(0, int(wert))
    except ValueError:
        return standard


# An die 0.0.0.0:8000 im Container gebunden (wie bisher über die Kommandozeile).
bind = "0.0.0.0:8000"

workers = max(1, _zahl("BINTAFELN_WORKER", 3))
timeout = max(30, _zahl("BINTAFELN_TIMEOUT", 120))

# Worker nach einer Weile neu starten, damit langsam anwachsender Speicher wieder frei wird. Mit
# etwas Streuung, damit nicht alle Worker gleichzeitig neu starten.
max_requests = _zahl("BINTAFELN_MAX_REQUESTS", 1000)
max_requests_jitter = max_requests // 10 if max_requests else 0

# Beim Beenden/Neustart etwas Luft lassen, damit laufende Anfragen sauber enden.
graceful_timeout = 30

# Wie bisher: kein Steuer-Socket, Zugriffsprotokoll auf die Standardausgabe.
accesslog = "-"
