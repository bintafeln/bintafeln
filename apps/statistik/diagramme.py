"""Diagramme als SVG, auf dem Server gezeichnet (ADR 0036): kein JavaScript, kein CDN.

Gestaltung: eine Achse, dezente Hilfslinien, schmale Säulen mit gerundetem Ende an der Spitze,
2px Abstand, 2px Linien, Punkte ≥ 8px; Werte beim Überfahren als Tooltip (<title>) und immer
zusätzlich als Tabelle unter dem Diagramm. Farben sind CSS-Klassen ``reihe-0`` … ``reihe-7``
(feste, auf Farbsehschwäche geprüfte Reihenfolge in bintafeln.css).
"""

import math
from html import escape

from django.utils.safestring import mark_safe

BREITE, HOEHE = 640, 260
LINKS, RECHTS, OBEN, UNTEN = 48, 12, 16, 34


def _zahl(wert: float, nachkomma: int = 0) -> str:
    text = f"{wert:,.{nachkomma}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _skala(maximum: float) -> tuple[float, list[float]]:
    """Runde Obergrenze (1/2/2,5/5 × 10^n) und 4 Hilfslinien."""
    if maximum <= 0:
        return 4, [0, 1, 2, 3, 4]
    roh = maximum / 4
    zehner = 10 ** math.floor(math.log10(roh))
    schritt = next(f * zehner for f in (1, 2, 2.5, 5, 10) if f * zehner >= roh)
    if maximum < 4 and schritt < 1:
        schritt = 1
    return schritt * 4, [schritt * i for i in range(5)]


def _rahmen(titel: str, inhalt: list[str], hoehe: int = HOEHE) -> str:
    # Alle Texte aus Daten (Namen, Beschriftungen) laufen vorher durch escape().
    return mark_safe(  # noqa: S308
        f'<svg class="diagramm" viewBox="0 0 {BREITE} {hoehe}" role="img" '
        f'aria-label="{escape(titel)}" preserveAspectRatio="xMidYMid meet">'
        + "".join(inhalt)
        + "</svg>"
    )


def _saeule(x, y, b, h, klasse, tooltip) -> str:
    """Säule mit 4px-Rundung oben, flach auf der Grundlinie."""
    if h <= 0:
        return ""
    r = min(4, b / 2, h)
    pfad = (
        f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
        f"H{x + b - r:.1f} Q{x + b:.1f},{y:.1f} {x + b:.1f},{y + r:.1f} V{y + h:.1f} Z"
    )
    return f'<path class="{klasse}" d="{pfad}"><title>{escape(tooltip)}</title></path>'


def _achse_y(obergrenze, linien, nachkomma) -> list[str]:
    teile = []
    innen = HOEHE - OBEN - UNTEN
    for wert in linien:
        y = OBEN + innen - innen * wert / obergrenze
        klasse = "achse" if wert == 0 else "gitter"
        teile.append(
            f'<line class="{klasse}" x1="{LINKS}" x2="{BREITE - RECHTS}" '
            f'y1="{y:.1f}" y2="{y:.1f}"/>'
        )
        teile.append(
            f'<text class="skala" x="{LINKS - 6}" y="{y + 4:.1f}" text-anchor="end">'
            f"{_zahl(wert, nachkomma if wert % 1 else 0)}</text>"
        )
    return teile


def saeulen(
    daten: list[tuple[str, float]],
    titel: str,
    einheit: str = "",
    nachkomma: int = 0,
    farbe: int = 0,
) -> str:
    """Senkrechte Säulen für eine Reihe (z. B. Abholungen je Monat)."""
    if not daten:
        return ""
    obergrenze, linien = _skala(max(w for _, w in daten))
    innen_b, innen_h = BREITE - LINKS - RECHTS, HOEHE - OBEN - UNTEN
    feld = innen_b / len(daten)
    b = max(2.0, min(28.0, feld - 2))
    teile = _achse_y(obergrenze, linien, nachkomma)
    jede = max(1, math.ceil(len(daten) / 14))  # Beschriftung ausdünnen
    groesster = max(range(len(daten)), key=lambda i: daten[i][1])
    for i, (name, wert) in enumerate(daten):
        x = LINKS + feld * i + (feld - b) / 2
        h = innen_h * wert / obergrenze
        y = OBEN + innen_h - h
        tip = f"{name}: {_zahl(wert, nachkomma)}{einheit}"
        teile.append(_saeule(x, y, b, h, f"reihe-{farbe}", tip))
        if i % jede == 0:
            teile.append(
                f'<text class="beschriftung" x="{x + b / 2:.1f}" y="{HOEHE - UNTEN + 16}" '
                f'text-anchor="middle">{escape(name)}</text>'
            )
        if i == groesster and wert > 0:  # sparsam: nur der höchste Wert direkt beschriftet
            teile.append(
                f'<text class="wert" x="{x + b / 2:.1f}" y="{y - 5:.1f}" '
                f'text-anchor="middle">{_zahl(wert, nachkomma)}</text>'
            )
    return _rahmen(titel, teile)


def balken(
    daten: list[tuple[str, float]],
    titel: str,
    einheit: str = "",
    nachkomma: int = 0,
    farbe: int = 0,
    maximum: float | None = None,
) -> str:
    """Waagerechte Balken mit Beschriftung links und Wert am Ende (Kategorien, Rangfolgen)."""
    if not daten:
        return ""
    zeile = 26
    hoehe = OBEN + zeile * len(daten) + 8
    links = 150
    breite = BREITE - links - 70
    groesste = maximum or max(w for _, w in daten) or 1
    teile = [f'<line class="achse" x1="{links}" x2="{links}" y1="{OBEN - 4}" y2="{hoehe - 8}"/>']
    for i, (name, wert) in enumerate(daten):
        y = OBEN + i * zeile
        w = breite * min(wert, groesste) / groesste
        kurz = name if len(name) <= 22 else name[:21] + "…"
        teile.append(
            f'<text class="beschriftung" x="{links - 8}" y="{y + 15}" '
            f'text-anchor="end">{escape(kurz)}<title>{escape(name)}</title></text>'
        )
        if w > 0:
            r = min(4, w, 9)
            pfad = (
                f"M{links},{y + 3} H{links + w - r:.1f} Q{links + w:.1f},{y + 3} "
                f"{links + w:.1f},{y + 3 + r} V{y + 21 - r} Q{links + w:.1f},{y + 21} "
                f"{links + w - r:.1f},{y + 21} H{links} Z"
            )
            teile.append(
                f'<path class="reihe-{farbe}" d="{pfad}"><title>{escape(name)}: '
                f"{_zahl(wert, nachkomma)}{escape(einheit)}</title></path>"
            )
        teile.append(
            f'<text class="wert" x="{links + w + 6:.1f}" y="{y + 16}">'
            f"{_zahl(wert, nachkomma)}{escape(einheit)}</text>"
        )
    return _rahmen(titel, teile, hoehe)


def linien(beschriftungen: list[str], serien, titel: str, einheit: str = "") -> str:
    """Verlauf mehrerer Reihen (je Ausgabestelle); Farbe folgt der Reihe, nicht dem Rang."""
    if not beschriftungen or not serien:
        return ""
    obergrenze, gitter = _skala(max((max(s.werte) for s in serien), default=0))
    innen_b, innen_h = BREITE - LINKS - RECHTS - 90, HOEHE - OBEN - UNTEN
    schritt = innen_b / max(1, len(beschriftungen) - 1)
    teile = _achse_y(obergrenze, gitter, 0)
    jede = max(1, math.ceil(len(beschriftungen) / 12))
    for i, name in enumerate(beschriftungen):
        if i % jede == 0:
            teile.append(
                f'<text class="beschriftung" x="{LINKS + schritt * i:.1f}" '
                f'y="{HOEHE - UNTEN + 16}" text-anchor="middle">{escape(name)}</text>'
            )
    endpunkte = []
    for s in serien:
        punkte = [
            (LINKS + schritt * i, OBEN + innen_h - innen_h * w / obergrenze)
            for i, w in enumerate(s.werte)
        ]
        pfad = " ".join(
            f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(punkte)
        )
        teile.append(f'<path class="linie linie-{s.farbe}" d="{pfad}"/>')
        for (x, y), w, b in zip(punkte, s.werte, beschriftungen, strict=True):
            teile.append(
                f'<circle class="punkt reihe-{s.farbe}" cx="{x:.1f}" cy="{y:.1f}" r="4">'
                f"<title>{escape(s.name)}, {escape(b)}: {_zahl(w)}{escape(einheit)}"
                "</title></circle>"
            )
        endpunkte.append((punkte[-1][1], s))
    # Gemeinsamen ersten Namensteil (z. B. „Ausgabestelle“) am Linienende weglassen
    ersten = {s.name.split(" ", 1)[0] for s in serien}
    gemeinsam = len(serien) > 1 and len(ersten) == 1 and all(" " in s.name for s in serien)
    # Direkte Beschriftung am Ende, ohne Überlappung (mind. 13px Abstand)
    letzte_y = -100.0
    for y, s in sorted(endpunkte, key=lambda e: e[0]):
        y = max(y, letzte_y + 13)
        letzte_y = y
        x = LINKS + schritt * (len(beschriftungen) - 1) + 8
        name = s.name.split(" ", 1)[1] if gemeinsam else s.name
        kurz = name if len(name) <= 12 else name[:11] + "…"
        teile.append(
            f'<text class="beschriftung" x="{x:.1f}" y="{y + 4:.1f}">{escape(kurz)}</text>'
        )
    return _rahmen(titel, teile)
