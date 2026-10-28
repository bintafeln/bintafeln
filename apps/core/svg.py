"""Hochgeladene SVG-Grafiken bereinigen: nur Zeichenelemente und harmlose Attribute bleiben.

Ein SVG ist ein Dokument und kann Skripte, Ereignis-Attribute (``onload``) oder Verweise auf
fremde Adressen enthalten. Öffnet jemand die Datei direkt, liefe ein Skript unter der Adresse der
Tafel. Deshalb wird jedes SVG beim Hochladen nach einer festen Liste neu geschrieben; alles
Unbekannte fällt weg. Dazu sendet Caddy für öffentliche Uploads eine strenge
Content-Security-Policy.
"""

import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
MAX_BYTES = 512 * 1024

ELEMENTE = {
    "svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "defs",
    "lineargradient", "radialgradient", "stop", "title", "desc", "use", "clippath", "mask",
    "symbol", "text", "tspan", "pattern",
}  # fmt: skip
ATTRIBUTE = {
    "id", "class", "viewbox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy",
    "r", "rx", "ry", "d", "points", "fill", "fill-opacity", "fill-rule", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-opacity", "stroke-dasharray",
    "stroke-dashoffset", "stroke-miterlimit", "opacity", "transform", "offset", "stop-color",
    "stop-opacity", "gradientunits", "gradienttransform", "spreadmethod", "fx", "fy",
    "clip-path", "clip-rule", "mask", "preserveaspectratio", "font-family", "font-size",
    "font-weight", "text-anchor", "dominant-baseline", "patternunits", "patterntransform",
    "href", "style", "display", "visibility", "version",
}  # fmt: skip
# url(...) nur auf Teile derselben Datei (#verlauf), nie auf fremde Adressen
FREMDE_URL = re.compile(r"url\(\s*['\"]?\s*(?!#)", re.IGNORECASE)
GEFAEHRLICH = re.compile(r"javascript:|expression\(|@import|<", re.IGNORECASE)


def _name(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def _wert_ok(name: str, wert: str) -> bool:
    if GEFAEHRLICH.search(wert) or FREMDE_URL.search(wert):
        return False
    return name != "href" or wert.startswith("#")


def _reinigen(element) -> ET.Element | None:
    ns, name = _name(element.tag)
    if ns not in ("", SVG_NS) or name.lower() not in ELEMENTE:
        return None
    neu = ET.Element(f"{{{SVG_NS}}}{name}")
    for schluessel, wert in element.attrib.items():
        a_ns, a_name = _name(schluessel)
        if a_ns not in ("", XLINK_NS) or a_name.lower() not in ATTRIBUTE:
            continue
        if _wert_ok(a_name.lower(), wert):
            neu.set(a_name, wert)  # xlink:href wird zu href
    neu.text = element.text if name.lower() in ("text", "tspan", "title", "desc") else None
    for kind in element:
        sauber = _reinigen(kind)
        if sauber is not None:
            sauber.tail = kind.tail if name.lower() in ("text", "tspan") else None
            neu.append(sauber)
    return neu


def bereinigen(daten: bytes) -> bytes | None:
    """Das bereinigte SVG oder None, wenn es kein lesbares SVG ist."""
    if len(daten) > MAX_BYTES or b"<!DOCTYPE" in daten.upper() or b"<!ENTITY" in daten.upper():
        return None
    try:
        # Ohne DOCTYPE/ENTITY (oben abgewiesen) gibt es keine Entitäten-Angriffe
        wurzel = ET.fromstring(daten)  # noqa: S314
    except ET.ParseError:
        return None
    if _name(wurzel.tag)[1].lower() != "svg":
        return None
    sauber = _reinigen(wurzel)
    ET.register_namespace("", SVG_NS)
    return ET.tostring(sauber, encoding="utf-8", xml_declaration=True)
