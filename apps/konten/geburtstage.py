"""Geburtstage der Mitarbeitenden (Team) – Kalender und „nächste Geburtstage".

Mitarbeitende sind die Personen im Adressbuch mit einem aktiven Konto, das nicht zu einer
Ausgabestelle gehört (ADR 0097). Das Geburtsdatum steht an der Adresse. Spender, Mitglieder ohne
Konto und Organisationen bleiben außen vor.
"""

import datetime as dt


def _mitarbeitende():
    from apps.adressen.models import Adresse

    return (
        Adresse.objects.filter(
            art=Adresse.Art.PERSON,
            konto__isnull=False,
            konto__is_active=True,
            konto__stelle__isnull=True,
            geburtsdatum__isnull=False,
        )
        .select_related("konto")
        .order_by("nachname", "vorname")
    )


def _name(a) -> str:
    return f"{a.vorname} {a.nachname}".strip() or a.nachname


def _dieses_jahr(geb: dt.date, jahr: int) -> dt.date:
    """Der Geburtstag im angegebenen Jahr. Der 29. Februar wird in Nicht-Schaltjahren am 28.
    Februar gefeiert, damit er nicht verschwindet."""
    try:
        return geb.replace(year=jahr)
    except ValueError:  # 29.02. in einem Nicht-Schaltjahr
        return dt.date(jahr, 2, 28)


def kalender(heute: dt.date | None = None) -> list[dict]:
    """Alle Mitarbeitenden mit Geburtstag, nach Monat gruppiert (Januar … Dezember), je Monat nach
    Tag sortiert. Jeder Eintrag: Name, Datum, wird-im-Jahr, ob heute."""
    heute = heute or dt.date.today()
    monate: list[dict] = [
        {"nummer": m, "name": MONATE[m - 1], "eintraege": []} for m in range(1, 13)
    ]
    for a in _mitarbeitende():
        geb = a.geburtsdatum
        schon_vorbei = (geb.month, geb.day) < (heute.month, heute.day)
        monate[geb.month - 1]["eintraege"].append(
            {
                "name": _name(a),
                "geburtsdatum": geb,
                "tag": geb.day,
                "wird": heute.year - geb.year + (1 if schon_vorbei else 0),
                "ist_heute": (geb.month, geb.day) == (heute.month, heute.day),
            }
        )
    for monat in monate:
        monat["eintraege"].sort(key=lambda e: (e["tag"], e["name"]))
    return monate


def naechste(tage: int = 14, heute: dt.date | None = None) -> list[dict]:
    """Mitarbeitende, die in den nächsten ``tage`` Tagen (einschließlich heute) Geburtstag haben,
    nach Datum sortiert. Jeder Eintrag: Name, nächster Geburtstag, wird-X-Jahre, in-Tagen, heute."""
    heute = heute or dt.date.today()
    ende = heute + dt.timedelta(days=tage)
    ergebnis = []
    for a in _mitarbeitende():
        geb = a.geburtsdatum
        naechster = _dieses_jahr(geb, heute.year)
        if naechster < heute:
            naechster = _dieses_jahr(geb, heute.year + 1)
        if naechster > ende:
            continue
        ergebnis.append(
            {
                "name": _name(a),
                "geburtsdatum": geb,
                "naechster": naechster,
                "wird": naechster.year - geb.year,
                "in_tagen": (naechster - heute).days,
                "ist_heute": naechster == heute,
            }
        )
    ergebnis.sort(key=lambda e: (e["naechster"], e["name"]))
    return ergebnis


MONATE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]  # fmt: skip
