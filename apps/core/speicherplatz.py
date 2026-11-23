"""Freier Platz auf der Festplatte des Servers (ADR 0169).

Gemessen wird die Platte, auf der die Dateien von bintafeln liegen (``MEDIA_ROOT``) – bei einem
gemieteten Server dessen Festplatte. Wird sie voll, kann bintafeln nichts mehr speichern; deshalb
warnt es vorher: ein Hinweis auf der Startseite für alle, die die Tafel einstellen dürfen, und
einmal je Stufe eine Mail an die unter „Mail-Empfänger“ gewählten Personen (``speicher_knapp``).
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

KNAPP, DRINGEND = "knapp", "dringend"


@dataclass(frozen=True)
class Stand:
    gesamt: int
    frei: int
    stufe: str  # "", KNAPP oder DRINGEND

    @property
    def belegt(self) -> int:
        return self.gesamt - self.frei

    @property
    def prozent_frei(self) -> int:
        return round(self.frei * 100 / self.gesamt) if self.gesamt else 0

    @property
    def prozent_belegt(self) -> int:
        return 100 - self.prozent_frei


def _platte() -> tuple[int, int] | None:
    """(gesamt, frei) in Bytes, oder ``None``, wenn es sich nicht lesen lässt."""
    ordner = Path(settings.MEDIA_ROOT).resolve()
    while not ordner.exists() and ordner != ordner.parent:
        ordner = ordner.parent  # der Ordner entsteht erst mit der ersten Datei
    try:
        nutzung = shutil.disk_usage(ordner)
    except OSError:
        return None
    return nutzung.total, nutzung.free


def stand() -> Stand | None:
    from apps.core.models import SpeicherWarnung

    platte = _platte()
    if platte is None or not platte[0]:
        return None
    gesamt, frei = platte
    e = SpeicherWarnung.laden()
    anteil = frei * 100 / gesamt
    dringend = min(e.dringend_unter, e.warnen_unter)
    stufe = DRINGEND if anteil < dringend else KNAPP if anteil < e.warnen_unter else ""
    return Stand(gesamt, frei, stufe)


def _gb(wert: int) -> str:
    return f"{wert / 1024**3:.1f}".replace(".", ",") + " GB"


def melden(s: Stand | None) -> bool:
    """Einmal je Stufe eine Mail: beim Unterschreiten der Warn- und noch einmal der dringenden
    Grenze. Ist wieder genug frei, beginnt es von vorn. Liefert, ob gerade gemeldet wurde."""
    from apps.core import benachrichtigung
    from apps.core.models import SpeicherWarnung, TafelEinstellungen

    if s is None:
        return False
    e = SpeicherWarnung.laden()
    if s.stufe == e.gemeldet or (s.stufe == KNAPP and e.gemeldet == DRINGEND):
        if s.stufe != e.gemeldet:  # von „dringend“ zurück auf „knapp“: merken, nicht erneut mailen
            e.gemeldet = s.stufe
            e.save(update_fields=["gemeldet"])
        return False
    e.gemeldet = s.stufe
    e.save(update_fields=["gemeldet"])
    if not s.stufe:
        return False
    an = benachrichtigung.empfaenger("speicher_knapp")
    if not an:
        return False
    name = TafelEinstellungen.laden().name
    dringend = s.stufe == DRINGEND
    betreff = ("bintafeln: Festplatte fast voll" if dringend
               else "bintafeln: Festplatte wird voll")  # fmt: skip
    zeilen = [
        f"Auf dem Server von bintafeln{f' ({name})' if name else ''} sind nur noch "
        f"{_gb(s.frei)} von {_gb(s.gesamt)} frei ({s.prozent_frei} %).",
        "",
        "Ist die Festplatte voll, kann bintafeln nichts mehr speichern." if dringend
        else "Bitte rechtzeitig Platz schaffen oder den Speicher beim Anbieter vergrößern.",
        "Was Platz braucht, steht in bintafeln unter Einstellungen → Systemsteuerung → Speicher "
        "und Fotos. Alte Sicherungen auf dem Server belegen oft am meisten.",
    ]  # fmt: skip
    benachrichtigung.melden("speicher_knapp", an, betreff, "\n".join(zeilen))
    return True
