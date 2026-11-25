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
                "adresse": a,
                "naechster": _dieses_jahr(geb, heute.year + (1 if schon_vorbei else 0)),
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
                "adresse": a,
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


def letzte(tage: int = 7, heute: dt.date | None = None) -> list[dict]:
    """Mitarbeitende, die in den letzten ``tage`` Tagen (ohne heute) Geburtstag hatten, der
    jüngste zuerst – zum Nachgratulieren. Jeder Eintrag: Name, Tag, wurde-X-Jahre, vor-Tagen."""
    heute = heute or dt.date.today()
    beginn = heute - dt.timedelta(days=tage)
    ergebnis = []
    for a in _mitarbeitende():
        geb = a.geburtsdatum
        letzter = _dieses_jahr(geb, heute.year)
        if letzter >= heute:
            letzter = _dieses_jahr(geb, heute.year - 1)
        if letzter < beginn:
            continue
        ergebnis.append(
            {
                "adresse": a,
                "name": _name(a),
                "geburtsdatum": geb,
                "letzter": letzter,
                "wurde": letzter.year - geb.year,
                "vor_tagen": (heute - letzter).days,
            }
        )
    ergebnis.sort(key=lambda e: (-e["letzter"].toordinal(), e["name"]))
    return ergebnis


# --- Geburtstagsbrief auf der Startseite (ADR 0170) ---------------------------------------------

GRUSS_TAGE = 30  # so lange bleibt gemerkt, dass ein Brief bestätigt wurde


def brief(benutzer, heute: dt.date | None = None) -> list[dict]:
    """Die Glückwünsche, die dieses Konto heute auf der Startseite als Brief bekommt: der eigene
    Geburtstag (heute oder gestern) und – mit dem Recht ``mitarbeitende.geburtstagsbrief`` – die
    aller Mitarbeitenden. Was das Konto schon bestätigt hat, fehlt. Der eigene steht vorn, heute
    vor gestern. Jeder Eintrag: adresse, tag, name, vorname, eigen, gestern, alter."""
    from apps.konten import rollen
    from apps.konten.models import GeburtstagGruss

    heute = heute or dt.date.today()
    tage = (heute, heute - dt.timedelta(days=1))
    alle = rollen.hat_recht(benutzer, "mitarbeitende.geburtstagsbrief")
    gemerkt = set(
        GeburtstagGruss.objects.filter(benutzer=benutzer, tag__in=tage).values_list(
            "adresse_id", "tag"
        )
    )
    ergebnis = []
    for a in _mitarbeitende():
        eigen = a.konto_id == benutzer.pk
        if not (eigen or alle):
            continue
        for tag in tage:
            if _dieses_jahr(a.geburtsdatum, tag.year) != tag or (a.pk, tag) in gemerkt:
                continue
            ergebnis.append(
                {
                    "adresse": a,
                    "tag": tag,
                    "name": _name(a),
                    "vorname": a.vorname or _name(a),
                    "eigen": eigen,
                    "gestern": tag != heute,
                    "alter": tag.year - a.geburtsdatum.year,
                }
            )
    ergebnis.sort(key=lambda e: (not e["eigen"], e["gestern"], e["name"]))
    return ergebnis


def gesehen(benutzer, eintraege: list[tuple[int, dt.date]], heute: dt.date | None = None) -> int:
    """Merkt für dieses Konto, dass es die Briefe bestätigt hat („Gratuliert“, „Danke!“). Nur was
    dem Konto gerade wirklich als Brief zusteht, wird gemerkt. Liefert die Anzahl."""
    from apps.konten.models import GeburtstagGruss

    wunsch = set(eintraege)
    anzahl = 0
    for e in brief(benutzer, heute):
        if (e["adresse"].pk, e["tag"]) in wunsch:
            GeburtstagGruss.objects.get_or_create(
                benutzer=benutzer, adresse=e["adresse"], tag=e["tag"]
            )
            anzahl += 1
    return anzahl


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Löscht die Merker bestätigter Briefe nach 30 Tagen."""
    from apps.konten.models import GeburtstagGruss

    heute = heute or dt.date.today()
    from apps.konten.models import GeburtstagMail

    alt = GeburtstagGruss.objects.filter(tag__lt=heute - dt.timedelta(days=GRUSS_TAGE))
    anzahl = alt.count()
    alt.delete()
    from apps.konten.models import GeburtstagVormerkung

    GeburtstagMail.objects.filter(tag__lt=heute - dt.timedelta(days=GRUSS_TAGE)).delete()
    # nicht gesendete Vormerkungen (Mailserver fiel aus) bleiben so lange zum Nachsenden von Hand
    GeburtstagVormerkung.objects.filter(tag__lt=heute - dt.timedelta(days=GRUSS_TAGE)).delete()
    return anzahl


MONATE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]  # fmt: skip
