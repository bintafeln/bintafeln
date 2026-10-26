"""Verschlüsselt abgelegte, nie öffentlich ausgelieferte Dateien (ADR 0017).

Die Dateien liegen unter MEDIA_ROOT/privat/<ordner>/ und werden mit dem Schlüssel aus
apps.core.geheimnis verschlüsselt. Ausgeliefert werden sie nur über Ansichten mit
Rechteprüfung, die jeden Abruf protokollieren.
"""

import io
import uuid
from pathlib import Path

from django.conf import settings

from apps.core import geheimnis

FOTO_ODER_PDF = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


class DateiFehler(ValueError):
    pass


def pfad(ordner: str, name: str) -> Path:
    return Path(settings.MEDIA_ROOT) / "privat" / ordner / name


def speichern(ordner: str, datei, *, typen=FOTO_ODER_PDF, max_mb=5) -> str:
    """Prüft und speichert eine hochgeladene Datei verschlüsselt; liefert den Dateinamen."""
    if datei.content_type not in typen:
        raise DateiFehler("Bitte ein Foto (JPG, PNG, WebP) oder ein PDF hochladen.")
    if datei.size > max_mb * 1024 * 1024:
        raise DateiFehler(f"Die Datei darf höchstens {max_mb} MB groß sein.")
    name = f"{uuid.uuid4().hex}.bin"
    ziel = pfad(ordner, name)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(
        geheimnis.bytes_verschluesseln(_foto_verkleinern(datei.read(), datei.content_type))
    )
    return name


def _foto_verkleinern(daten: bytes, typ: str) -> bytes:
    """Fotos nach den Foto-Einstellungen der Tafel verkleinern (ADR 0064); PDFs bleiben."""
    from apps.core import bilder
    from apps.core.models import FotoEinstellungen

    e = FotoEinstellungen.laden()
    return bilder.foto_verkleinern(daten, typ, e.kante, e.qualitaet, e.graustufen)


def lesen(ordner: str, name: str) -> bytes | None:
    """Entschlüsselter Inhalt oder None, wenn nicht vorhanden oder nicht mehr lesbar."""
    if not name:
        return None
    datei = pfad(ordner, name)
    return geheimnis.bytes_entschluesseln(datei.read_bytes()) if datei.exists() else None


def loeschen(ordner: str, name: str) -> None:
    if name:
        pfad(ordner, name).unlink(missing_ok=True)


# --- Speicher: vorhandene Fotos verkleinern, Originale aufräumen (ADR 0064) ---------------------

ORIGINAL = ".orig"  # verschlüsselte Originaldatei neben der verkleinerten
ERLEDIGT = "verkleinert.json"  # welche Datei mit welchen Einstellungen verkleinert wurde


def _wurzel() -> Path:
    return Path(settings.MEDIA_ROOT) / "privat"


def _dateien():
    wurzel = _wurzel()
    if not wurzel.is_dir():
        return []
    return sorted(p for p in wurzel.rglob("*.bin") if p.is_file())


def bestand() -> list[dict]:
    """Je Ordner: Anzahl Dateien, belegter Platz und Platz der aufbewahrten Originale."""
    ordner = {}
    for p in _wurzel().rglob("*") if _wurzel().is_dir() else []:
        if not p.is_file() or p.name == ERLEDIGT:
            continue
        name = p.relative_to(_wurzel()).parts[0]
        z = ordner.setdefault(name, {"ordner": name, "anzahl": 0, "bytes": 0, "originale": 0})
        if p.name.endswith(ORIGINAL):
            z["originale"] += p.stat().st_size
        else:
            z["anzahl"] += 1
            z["bytes"] += p.stat().st_size
    return sorted(ordner.values(), key=lambda z: -z["bytes"])


def _schluessel(e) -> str:
    return f"{e.kante}-{e.qualitaet}-{int(e.graustufen)}"


def vorhandene_verkleinern(grenze: int = 200) -> dict:
    """Verkleinert bis zu ``grenze`` vorhandene Fotos nach den aktuellen Einstellungen. Quelle ist
    immer das Original (``.orig``), so lassen sich geänderte Einstellungen erneut anwenden. Das
    Original bleibt liegen, bis ``originale_loeschen()`` es entfernt."""
    import json

    from apps.core import bilder
    from apps.core.models import FotoEinstellungen

    e = FotoEinstellungen.laden()
    schluessel = _schluessel(e)
    liste = _wurzel() / ERLEDIGT
    erledigt = json.loads(liste.read_text()) if liste.exists() else {}
    ergebnis = {"verkleinert": 0, "gespart": 0, "offen": 0}
    for datei in _dateien():
        rel = datei.relative_to(_wurzel()).as_posix()
        if erledigt.get(rel) == schluessel:
            continue
        if ergebnis["verkleinert"] >= grenze:
            ergebnis["offen"] += 1
            continue
        original = datei.with_name(datei.name + ORIGINAL)
        quelle = original if original.exists() else datei
        daten = geheimnis.bytes_entschluesseln(quelle.read_bytes())
        erledigt[rel] = schluessel
        typ = _foto_typ(daten) if daten is not None else None
        if typ is None:
            continue  # PDF, nicht lesbar oder kein Foto
        neu = bilder.foto_verkleinern(daten, typ, e.kante, e.qualitaet, e.graustufen)
        vorher = datei.stat().st_size
        if neu is daten and quelle is datei:
            continue  # schon klein genug
        if not original.exists():
            datei.rename(original)
        datei.write_bytes(geheimnis.bytes_verschluesseln(neu))
        ergebnis["verkleinert"] += 1
        ergebnis["gespart"] += vorher - datei.stat().st_size
    liste.parent.mkdir(parents=True, exist_ok=True)
    liste.write_text(json.dumps(erledigt))
    return ergebnis


def _foto_typ(daten: bytes) -> str | None:
    from PIL import Image

    from apps.core import bilder

    try:
        format_ = Image.open(io.BytesIO(daten)).format
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    return next((t for t, f in bilder.FORMATE.items() if f == format_), None)


def originale_loeschen() -> tuple[int, int]:
    """Löscht die aufbewahrten Originale; liefert (Anzahl, freigegebene Bytes)."""
    anzahl = frei = 0
    for p in _wurzel().rglob(f"*{ORIGINAL}") if _wurzel().is_dir() else []:
        frei += p.stat().st_size
        p.unlink()
        anzahl += 1
    return anzahl, frei
