"""Gesetzliche Feiertage je Bundesland (ADR 0019).

Berücksichtigt sind landesweit geltende Feiertage. Feiertage nur in einzelnen Gemeinden (z. B.
Mariä Himmelfahrt in Teilen Bayerns, Fronleichnam in Teilen Sachsens und Thüringens,
Augsburger Friedensfest) fehlen; sie lassen sich wie bisher von Hand berücksichtigen.
"""

import datetime as dt
from functools import lru_cache

BUNDESLAENDER = [
    ("BW", "Baden-Württemberg"),
    ("BY", "Bayern"),
    ("BE", "Berlin"),
    ("BB", "Brandenburg"),
    ("HB", "Bremen"),
    ("HH", "Hamburg"),
    ("HE", "Hessen"),
    ("MV", "Mecklenburg-Vorpommern"),
    ("NI", "Niedersachsen"),
    ("NW", "Nordrhein-Westfalen"),
    ("RP", "Rheinland-Pfalz"),
    ("SL", "Saarland"),
    ("SN", "Sachsen"),
    ("ST", "Sachsen-Anhalt"),
    ("SH", "Schleswig-Holstein"),
    ("TH", "Thüringen"),
]


def ostersonntag(jahr: int) -> dt.date:
    """Gregorianischer Ostersonntag (Algorithmus nach Gauß in der Form von Meeus/Jones/Butcher)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    monat = (h + m - 7 * n + 114) // 31
    tag = (h + m - 7 * n + 114) % 31 + 1
    return dt.date(jahr, monat, tag)


def _buss_und_bettag(jahr: int) -> dt.date:
    """Mittwoch vor dem 23. November."""
    tag = dt.date(jahr, 11, 22)
    return tag - dt.timedelta(days=(tag.weekday() - 2) % 7)


@lru_cache(maxsize=256)
def feiertage(jahr: int, land: str) -> dict[dt.date, str]:
    """Alle gesetzlichen Feiertage eines Jahres im Bundesland; leeres Land = keine."""
    if not land:
        return {}
    ostern = ostersonntag(jahr)

    def o(tage):
        return ostern + dt.timedelta(days=tage)

    tage = {
        dt.date(jahr, 1, 1): "Neujahr",
        o(-2): "Karfreitag",
        o(1): "Ostermontag",
        dt.date(jahr, 5, 1): "Tag der Arbeit",
        o(39): "Christi Himmelfahrt",
        o(50): "Pfingstmontag",
        dt.date(jahr, 10, 3): "Tag der Deutschen Einheit",
        dt.date(jahr, 12, 25): "1. Weihnachtstag",
        dt.date(jahr, 12, 26): "2. Weihnachtstag",
    }

    def wenn(laender, datum, name, ab=None):
        if land in laender and (ab is None or jahr >= ab):
            tage[datum] = name

    wenn({"BW", "BY", "ST"}, dt.date(jahr, 1, 6), "Heilige Drei Könige")
    wenn({"BE"}, dt.date(jahr, 3, 8), "Internationaler Frauentag", ab=2019)
    wenn({"MV"}, dt.date(jahr, 3, 8), "Internationaler Frauentag", ab=2023)
    wenn({"BB"}, ostern, "Ostersonntag")
    wenn({"BB"}, o(49), "Pfingstsonntag")
    wenn({"BW", "BY", "HE", "NW", "RP", "SL"}, o(60), "Fronleichnam")
    wenn({"SL"}, dt.date(jahr, 8, 15), "Mariä Himmelfahrt")
    wenn({"TH"}, dt.date(jahr, 9, 20), "Weltkindertag", ab=2019)
    wenn({"BB", "MV", "SN", "ST", "TH"}, dt.date(jahr, 10, 31), "Reformationstag")
    wenn({"HB", "HH", "NI", "SH"}, dt.date(jahr, 10, 31), "Reformationstag", ab=2018)
    if jahr == 2017:  # 500 Jahre Reformation: einmalig bundesweit
        tage[dt.date(2017, 10, 31)] = "Reformationstag"
    wenn({"BW", "BY", "NW", "RP", "SL"}, dt.date(jahr, 11, 1), "Allerheiligen")
    wenn({"SN"}, _buss_und_bettag(jahr), "Buß- und Bettag")
    return dict(sorted(tage.items()))


def ist_feiertag(datum: dt.date, land: str) -> bool:
    return datum in feiertage(datum.year, land)
