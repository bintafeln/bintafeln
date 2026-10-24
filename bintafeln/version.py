"""Version der laufenden Installation (ADR 0023).

`./betrieb update` schreibt sie vor dem Bauen in die Datei VERSION, z. B. "2026.10.3" oder
"main-1a2b3c4" für einen Stand zwischen zwei Versionen.
"""

from functools import cache
from pathlib import Path

DATEI = Path(__file__).resolve().parent.parent / "VERSION"


@cache
def version() -> str:
    try:
        return DATEI.read_text(encoding="utf-8").strip() or "unbekannt"
    except OSError:
        return "Entwicklungsstand"
