"""Farbschema der Tafel: aus einer gewählten Farbe die übrigen Töne ableiten."""

import re

STANDARDFARBE = "#e8710a"  # Tafel-Orange
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _rgb(farbe: str) -> tuple[int, int, int]:
    if not _HEX.match(farbe or ""):
        farbe = STANDARDFARBE
    return tuple(int(farbe[i : i + 2], 16) for i in (1, 3, 5))


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0, min(255, k))):02x}" for k in rgb)


def _mischen(rgb, ziel: int, anteil: float):
    return [k + (ziel - k) * anteil for k in rgb]


def _leuchtdichte(rgb) -> float:
    def linear(k):
        k /= 255
        return k / 12.92 if k <= 0.03928 else ((k + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(k) for k in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def farbtoene(farbe: str) -> dict[str, str]:
    """Akzent, dunkler Ton für Links und Text, heller Ton für Flächen, Schrift auf dem Akzent.

    Weiße Schrift, solange sie genug Kontrast hat (3:1, wie bei großer, fetter Schrift
    üblich); sonst dunkle Schrift.
    """
    rgb = _rgb(farbe)
    weiss_kontrast = 1.05 / (_leuchtdichte(rgb) + 0.05)
    return {
        "akzent": _hex(rgb),
        "akzent_dunkel": _hex(_mischen(rgb, 0, 0.35)),
        "erfolg": _hex(_mischen(rgb, 255, 0.86)),
        "fokus": _hex(_mischen(rgb, 255, 0.5)),
        "auf_akzent": "#ffffff" if weiss_kontrast >= 3 else "#1f2421",
    }
