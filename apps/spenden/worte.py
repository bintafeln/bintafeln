"""Beträge in Worten für Zuwendungsbestätigungen („Betrag in Buchstaben“)."""

from decimal import ROUND_HALF_UP, Decimal

_EINER = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun",
          "zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn",
          "achtzehn", "neunzehn"]  # fmt: skip
_ZEHNER = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig",
           "neunzig"]  # fmt: skip


def _unter_hundert(n: int, ein: bool) -> str:
    """ein=True: „ein“ statt „eins“ (einhundert, eintausend, einundzwanzig)."""
    if n == 1:
        return "ein" if ein else "eins"
    if n < 20:
        return _EINER[n]
    zehner, einer = divmod(n, 10)
    if einer == 0:
        return _ZEHNER[zehner]
    return ("ein" if einer == 1 else _EINER[einer]) + "und" + _ZEHNER[zehner]


def _unter_tausend(n: int, ein: bool = False) -> str:
    hunderter, rest = divmod(n, 100)
    teil = _unter_hundert(hunderter, True) + "hundert" if hunderter else ""
    if rest:
        teil += _unter_hundert(rest, ein)
    return teil


def zahl(n: int) -> str:
    """Ganze Zahl ab 0 in Worten, z. B. 1250 -> „eintausendzweihundertfünfzig“."""
    if n < 0:
        raise ValueError("nur Zahlen ab 0")
    if n == 0:
        return "null"
    millionen, rest = divmod(n, 1_000_000)
    tausender, rest = divmod(rest, 1000)
    teile = []
    if millionen:
        teile.append("eine Million" if millionen == 1 else
                     f"{_unter_tausend(millionen)} Millionen")  # fmt: skip
    wort = ""
    if tausender:
        wort += _unter_tausend(tausender, True) + "tausend"
    if rest:
        wort += _unter_tausend(rest)
    if wort:
        teile.append(wort)
    return " ".join(teile)


def euro(betrag: Decimal) -> str:
    """Z. B. 150,50 -> „einhundertfünfzig Euro und fünfzig Cent“; 1 -> „ein Euro“."""
    betrag = Decimal(betrag).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    euros = int(betrag)
    cent = int((betrag - euros) * 100)
    text = ("ein" if euros == 1 else zahl(euros)) + " Euro"
    if cent:
        text += " und " + ("ein" if cent == 1 else zahl(cent)) + " Cent"
    return text
