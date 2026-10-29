"""Gestaltete Serienbrief-Vorlagen (ADR 0088): HTML aus dem Editor, Platzhalter, PDF und E-Mail.

Gespeichert wird bereinigtes HTML (``apps.core.html.bereinigen``), Platzhalter stehen darin als
``{anrede}``. Ältere Vorlagen aus reinem Text (Absätze durch Leerzeilen) wandelt ``als_html()``
beim Anzeigen und Verwenden in Absätze um.

Für das PDF übersetzt ``flowables()`` das HTML in ReportLab-Bausteine: fett, kursiv,
unterstrichen, Text- und Markierfarbe, Schriftgröße, Ausrichtung je Absatz, Überschriften,
Listen und farbige Kästen. Was es nicht kennt, erscheint als normaler Text.
"""

import re
from html import escape as xml_escape
from html.parser import HTMLParser

from django.utils.html import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from apps.core.html import als_text, bereinigen, ist_html
from apps.core.pdf import TEXT

BRIEF = ParagraphStyle(
    "brief", parent=TEXT, fontSize=10.5, leading=14, spaceAfter=3 * mm, autoLeading="max"
)
UEBERSCHRIFTEN = {"h1": 1.6, "h2": 1.3, "h3": 1.15, "h4": 1.05}
AUSRICHTUNG = {"left": TA_LEFT, "start": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT,
               "end": TA_RIGHT, "justify": TA_JUSTIFY}  # fmt: skip
# Schriftgrößen wie im Browser (16 px = normal), damit PDF und Editor gleich wirken
GROESSEN = {"xx-small": 0.6, "x-small": 0.625, "small": 0.8125, "medium": 1.0, "large": 1.125,
            "x-large": 1.5, "xx-large": 2.0, "smaller": 0.85, "larger": 1.2}  # fmt: skip
BLOECKE = {"p", "div", "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "table", "tr",
           "thead", "tbody", "header", "footer", "section", "nav", "hr"}  # fmt: skip
LEER = {"br", "hr", "img"}

_PLATZHALTER_SPAN = re.compile(
    r'<span\b[^>]*\bdata-platzhalter="(\w+)"[^>]*>.*?</span>', re.IGNORECASE | re.DOTALL
)


# --- Vorlagentext ------------------------------------------------------------------------------


def als_html(text: str) -> str:
    """HTML der Vorlage; reiner Text (ältere Vorlagen) wird zu Absätzen mit Zeilenumbrüchen."""
    text = text or ""
    if ist_html(text):
        return text
    absaetze = [a.strip() for a in text.replace("\r\n", "\n").split("\n\n")]
    return "".join(f"<p>{escape(a).replace(chr(10), '<br>')}</p>" for a in absaetze if a)


def speichern(text: str) -> str:
    """Was der Editor schickt, bereinigt; Platzhalter-Felder werden wieder zu ``{name}``."""
    return str(bereinigen(_PLATZHALTER_SPAN.sub(r"{\1}", als_html(text))))


def einsetzen(text: str, werte: dict) -> str:
    """Setzt {platzhalter} ins HTML ein, Werte immer maskiert (Empfängerdaten sind Fremddaten).

    Unbekannte Platzhalter bleiben stehen, damit Tippfehler auffallen. Das Ergebnis ist
    bereinigtes HTML.
    """

    def ersetzen(treffer):
        wert = werte.get(treffer.group(1))
        return treffer.group(0) if wert is None else str(escape(str(wert)))

    return str(bereinigen(re.sub(r"\{(\w+)\}", ersetzen, als_html(text))))


def mail_html(brief: str, fusszeile: str = "") -> str:
    """Ganze HTML-Mail aus dem eingesetzten Brief und der Fußzeile der Vorlage."""
    fuss = ""
    if fusszeile and fusszeile.strip():
        fuss = (
            '<hr style="border:0;border-top:1px solid #ccc;margin:24px 0 8px">'
            f'<div style="font-size:12px;color:#666">{bereinigen(als_html(fusszeile))}</div>'
        )
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8"></head>'
        '<body style="font-family:Helvetica,Arial,sans-serif;font-size:15px;line-height:1.45;'
        f'color:#222;max-width:42rem">{bereinigen(brief)}{fuss}</body></html>'
    )


def mail_text(html: str) -> str:
    """Klartext-Fassung der Mail (für Mailprogramme ohne HTML)."""
    html = re.sub(r"(?i)<li[^>]*>", "\n• ", html)
    html = re.sub(r"(?i)</(p|h[1-4]|div)>", "\n\n", html)
    return als_text(html)


# --- HTML in ReportLab-Bausteine -----------------------------------------------------------------


class _Knoten:
    def __init__(self, tag: str, attrs=None, eltern=None):
        self.tag, self.eltern = tag, eltern
        self.attrs = dict(attrs or [])
        self.kinder: list = []  # _Knoten oder str


class _Leser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.wurzel = _Knoten("body")
        self.aktuell = self.wurzel

    def handle_starttag(self, tag, attrs):
        knoten = _Knoten(tag, attrs, self.aktuell)
        self.aktuell.kinder.append(knoten)
        if tag not in LEER:
            self.aktuell = knoten

    def handle_startendtag(self, tag, attrs):
        self.aktuell.kinder.append(_Knoten(tag, attrs, self.aktuell))

    def handle_endtag(self, tag):
        knoten = self.aktuell
        while knoten is not self.wurzel and knoten.tag != tag:
            knoten = knoten.eltern
        if knoten is not self.wurzel:
            self.aktuell = knoten.eltern

    def handle_data(self, data):
        self.aktuell.kinder.append(data)


def _stil(knoten: _Knoten) -> dict:
    stil = {}
    for teil in (knoten.attrs.get("style") or "").split(";"):
        name, _, wert = teil.partition(":")
        if wert.strip():
            stil[name.strip().lower()] = wert.strip().lower()
    return stil


def farbe(wert: str | None) -> str | None:
    """CSS-Farbe als #rrggbb, sonst None (auch für alles Unbekannte)."""
    if not wert:
        return None
    wert = wert.strip().lower()
    rgb = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)", wert)
    if rgb:
        if rgb.group(4) is not None and float(rgb.group(4)) == 0:
            return None  # durchsichtig
        return "#" + "".join(f"{min(int(rgb.group(i)), 255):02x}" for i in (1, 2, 3))
    if re.fullmatch(r"#[0-9a-f]{3}", wert):
        return "#" + "".join(z * 2 for z in wert[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", wert):
        return wert
    if re.fullmatch(r"[a-z]+", wert) and wert not in ("transparent", "inherit", "initial"):
        try:
            return colors.toColor(wert).hexval().replace("0x", "#")
        except ValueError:
            return None
    return None


def _groesse(wert: str | None, basis: float) -> float | None:
    if not wert:
        return None
    if wert in GROESSEN:
        return round(basis * GROESSEN[wert], 1)
    zahl = re.fullmatch(r"([\d.]+)\s*(px|pt|em|rem|%)", wert)
    if not zahl:
        return None
    n, einheit = float(zahl.group(1)), zahl.group(2)
    faktor = {"px": n / 16, "pt": n / 12, "em": n, "rem": n, "%": n / 100}[einheit]
    return round(basis * min(max(faktor, 0.5), 3), 1)


class _Umsetzer:
    """Läuft durch den HTML-Baum und sammelt Absätze, Listen und Kästen."""

    def __init__(self, breite: float, grund: ParagraphStyle):
        self.breite, self.grund = breite, grund

    # Inline-Inhalt als ReportLab-Absatzmarkup
    def inline(self, knoten: _Knoten, groesse: float) -> str:
        teile = []
        for kind in knoten.kinder:
            if isinstance(kind, str):
                teile.append(xml_escape(re.sub(r"\s+", " ", kind), quote=False))
            elif kind.tag == "br":
                teile.append("<br/>")
            elif kind.tag in LEER or kind.tag in ("script", "style"):
                continue
            else:
                teile.append(self.auszeichnen(kind, groesse))
        return "".join(teile)

    def auszeichnen(self, knoten: _Knoten, groesse: float) -> str:
        stil = _stil(knoten)
        auf, zu = [], []

        def paar(a, z):
            auf.append(a)
            zu.insert(0, z)

        tag = knoten.tag
        if tag in ("b", "strong", "th") or stil.get("font-weight") in (
            "bold",
            "bolder",
            "600",
            "700",
            "800",
            "900",
        ):
            paar("<b>", "</b>")
        if tag in ("i", "em") or stil.get("font-style") == "italic":
            paar("<i>", "</i>")
        if tag == "u" or "underline" in stil.get("text-decoration", ""):
            paar("<u>", "</u>")
        if tag in ("s", "strike", "del") or "line-through" in stil.get("text-decoration", ""):
            paar("<strike>", "</strike>")
        if tag == "sub":
            paar("<sub>", "</sub>")
        if tag == "sup":
            paar("<super>", "</super>")
        neu = _groesse(stil.get("font-size"), self.grund.fontSize)
        if tag == "small" and not neu:
            neu = round(groesse * 0.85, 1)
        schrift = []
        if neu:
            schrift.append(f'size="{neu}"')
            groesse = neu
        if f := farbe(stil.get("color")):
            schrift.append(f'color="{f}"')
        if f := farbe(stil.get("background-color")):
            schrift.append(f'backColor="{f}"')
        if schrift:
            paar(f"<font {' '.join(schrift)}>", "</font>")
        innen = self.inline(knoten, groesse)
        if tag in BLOECKE and tag not in ("hr",):  # Block in einer Zeile: neue Zeile
            innen = f"<br/>{innen}"
        return "".join(auf) + innen + "".join(zu)

    def absatz(self, markup: str, stil: ParagraphStyle, aufzaehlung=None):
        if not re.sub(r"<br/>|\s|&nbsp;", "", markup) and aufzaehlung is None:
            return Spacer(1, stil.leading) if "<br/>" in markup else None
        if markup.startswith("<br/>"):
            markup = markup[5:]
        try:
            return Paragraph(markup, stil, bulletText=aufzaehlung)
        except ValueError:  # Markup, das ReportLab nicht versteht: lieber als reiner Text
            text = re.sub(r"<[^>]+>", "", markup.replace("<br/>", "\n"))
            return Paragraph(xml_escape(text).replace("\n", "<br/>"), stil, bulletText=aufzaehlung)

    def bloecke(self, knoten: _Knoten, stil: ParagraphStyle, einzug=0.0) -> list:
        """Flowables für den Inhalt von ``knoten`` (Text dazwischen wird zu Absätzen)."""
        ergebnis, puffer = [], _Knoten("span")

        def leeren():
            if puffer.kinder:
                f = self.absatz(self.inline(puffer, stil.fontSize), stil)
                if f:
                    ergebnis.append(f)
                puffer.kinder = []

        for kind in knoten.kinder:
            if isinstance(kind, str) or kind.tag not in BLOECKE:
                if isinstance(kind, str) and not puffer.kinder and not kind.strip():
                    continue  # Leerraum zwischen Blöcken
                puffer.kinder.append(kind)
                continue
            leeren()
            ergebnis.extend(self.block(kind, stil, einzug))
        leeren()
        return ergebnis

    def _absatzstil(self, knoten: _Knoten, stil: ParagraphStyle, einzug: float, **mehr):
        css = _stil(knoten)
        werte = {"leftIndent": einzug, "bulletIndent": max(einzug - 5 * mm, 0)} | mehr
        if css.get("text-align") in AUSRICHTUNG:
            werte["alignment"] = AUSRICHTUNG[css["text-align"]]
        if f := farbe(css.get("color")):
            werte["textColor"] = colors.HexColor(f)
        if g := _groesse(css.get("font-size"), stil.fontSize):
            werte |= {"fontSize": g, "leading": g * 1.33}
        return ParagraphStyle(f"{stil.name}-{knoten.tag}", parent=stil, **werte)

    def block(self, knoten: _Knoten, stil: ParagraphStyle, einzug: float) -> list:
        tag, css = knoten.tag, _stil(knoten)
        if tag == "hr":
            return [HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=2 * mm,
                               spaceAfter=3 * mm)]  # fmt: skip
        hintergrund = farbe(css.get("background-color"))
        if tag == "div" and (hintergrund or "kasten" in (knoten.attrs.get("class") or "")):
            return [self.kasten(knoten, stil, einzug, hintergrund or "#fdf3d8")]
        if tag in UEBERSCHRIFTEN:
            g = round(stil.fontSize * UEBERSCHRIFTEN[tag], 1)
            eigen = self._absatzstil(
                knoten, stil, einzug, fontName="Helvetica-Bold", fontSize=g, leading=g * 1.3,
                spaceBefore=2 * mm, spaceAfter=2 * mm,
            )  # fmt: skip
            return self.bloecke(knoten, eigen, einzug)
        if tag in ("ul", "ol"):
            return self.liste(knoten, stil, einzug + 6 * mm)
        if tag == "li":  # Listenpunkt ohne Liste
            return self.bloecke(knoten, stil, einzug)
        if tag == "blockquote":
            return self.bloecke(knoten, self._absatzstil(knoten, stil, einzug + 8 * mm),
                                einzug + 8 * mm)  # fmt: skip
        if tag == "tr":  # Tabellenzeile als Zeile mit Abständen
            zellen = [self.inline(k, stil.fontSize) for k in knoten.kinder
                      if isinstance(k, _Knoten) and k.tag in ("td", "th")]  # fmt: skip
            zeilenstil = self._absatzstil(knoten, stil, einzug)
            f = self.absatz("&nbsp;&nbsp;&nbsp;".join(zellen), zeilenstil)
            return [f] if f else []
        return self.bloecke(knoten, self._absatzstil(knoten, stil, einzug), einzug)

    def liste(self, knoten: _Knoten, stil: ParagraphStyle, einzug: float) -> list:
        start = knoten.attrs.get("start") or "1"
        ergebnis, nummer = [], int(start) - 1 if start.isdigit() else 0
        punkt_stil = ParagraphStyle(f"{stil.name}-li", parent=stil, leftIndent=einzug,
                                    bulletIndent=einzug - 5 * mm, spaceAfter=1 * mm)  # fmt: skip
        for kind in knoten.kinder:
            if not isinstance(kind, _Knoten) or kind.tag != "li":
                if isinstance(kind, _Knoten) and kind.tag in ("ul", "ol"):
                    ergebnis.extend(self.liste(kind, stil, einzug + 6 * mm))
                continue
            nummer += 1
            zeichen = f"{nummer}." if knoten.tag == "ol" else "•"
            eigen = self._absatzstil(kind, punkt_stil, einzug, bulletIndent=einzug - 5 * mm,
                                     spaceAfter=1 * mm)  # fmt: skip
            inhalt = self.bloecke(kind, eigen, einzug)
            if inhalt and isinstance(inhalt[0], Paragraph):
                inhalt[0] = Paragraph(inhalt[0].text, inhalt[0].style, bulletText=zeichen)
            else:
                inhalt.insert(0, Paragraph("", eigen, bulletText=zeichen))
            ergebnis.extend(inhalt)
        if ergebnis:
            ergebnis.append(Spacer(1, 2 * mm))
        return ergebnis

    def kasten(self, knoten: _Knoten, stil: ParagraphStyle, einzug: float, hintergrund: str):
        breite = self.breite - einzug
        innen = _Umsetzer(breite - 8 * mm, self.grund).bloecke(knoten, stil, 0)
        if innen and isinstance(innen[-1], Paragraph):  # kein Abstand unten im Kasten
            letzter = innen[-1]
            letzter.style = ParagraphStyle(f"{letzter.style.name}-ende", parent=letzter.style,
                                           spaceAfter=0)  # fmt: skip
        tabelle = Table([[innen or ""]], colWidths=[breite], hAlign="RIGHT" if einzug else "LEFT")
        tabelle.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(hintergrund)),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
            ("ROUNDEDCORNERS", [2 * mm] * 4),
        ]))  # fmt: skip
        tabelle.spaceAfter = 3 * mm
        return tabelle


def flowables(html: str, breite: float, grund: ParagraphStyle = BRIEF) -> list:
    """Bereinigtes HTML (bzw. alter Text) als ReportLab-Flowables für die Breite ``breite``."""
    leser = _Leser()
    leser.feed(str(bereinigen(als_html(html))))
    leser.close()
    return _Umsetzer(breite, grund).bloecke(leser.wurzel, grund)


# --- Für Briefe und Mails aus einer Vorlage ------------------------------------------------------


def brief(vorlage, empfaenger, allgemein: dict) -> tuple[str, str]:
    """(Betreff, HTML) für einen Empfänger: Betreff als Text, Brief als bereinigtes HTML."""
    from apps.serienbriefe.empfaenger import einsetzen as text_einsetzen

    werte = allgemein | empfaenger.werte
    return text_einsetzen(vorlage.betreff, empfaenger, allgemein), einsetzen(vorlage.text, werte)


def mail(vorlage, empfaenger, allgemein: dict) -> tuple[str, str, str]:
    """(Betreff, Klartext, HTML) für ``apps.core.mail.senden(betreff, text, an, html=…)``."""
    betreff, html = brief(vorlage, empfaenger, allgemein)
    ganz = mail_html(html, vorlage.fusszeile)
    fuss = mail_text(str(bereinigen(als_html(vorlage.fusszeile or ""))))
    return betreff, mail_text(html) + (f"\n\n-- \n{fuss}" if fuss else ""), ganz
