"""Was ein Aushang-Monitor zeigt (ADR 0080): die Folien der Seiten im gewählten Zeitraum."""

import datetime as dt

from apps.aushang.models import Aushang, AushangSeite
from apps.core import module


def zeitraum(heute: dt.date, monate: int) -> tuple[dt.date, dt.date]:
    """Ab heute bis zum Ende dieses Monats bzw. des nächsten (vergangene Tage zeigt der Monitor
    nicht; am Monatsende ist so schon der nächste Monat zu sehen)."""
    erster = heute.replace(day=1)
    for _ in range(monate):
        erster = (erster + dt.timedelta(days=32)).replace(day=1)
    return heute, erster - dt.timedelta(days=1)


def folien(aushang: Aushang, heute: dt.date) -> list[tuple[str, str]]:
    """[(titel, html)] aller Seiten; Seiten ausgeschalteter Module fallen weg."""
    arten = module.aushangseiten()
    ergebnis = []
    for seite in aushang.seiten.all():
        art = arten.get(seite.art)
        if art:
            ergebnis += art.folien(seite.wert, *zeitraum(heute, seite.monate))
    return ergebnis


def bezeichnung(seite: AushangSeite, arten: dict | None = None) -> str:
    """Für die Einstellungsseite, z. B. „Dienstplan einer Ausgabestelle: Mitte“."""
    arten = module.aushangseiten() if arten is None else arten
    art = arten.get(seite.art)
    if art is None:
        return f"{seite.art} (Modul ausgeschaltet)"
    text = dict(art.auswahl()).get(seite.wert, seite.wert)
    return f"{art.titel}: {text}" if text else art.titel


def wahlmoeglichkeiten(benutzer) -> list[tuple[str, str]]:
    """Seiten, die ``benutzer`` auf einen Aushang setzen darf: [("art:wert", text)]."""
    from apps.konten import rollen

    ergebnis = []
    for art in module.aushangseiten().values():
        if not rollen.hat_recht(benutzer, art.recht):
            continue
        auswahl = art.auswahl()
        if auswahl:
            ergebnis += [
                (f"{art.kennung}:{wert}", f"{art.titel}: {text}") for wert, text in auswahl
            ]
        else:
            ergebnis.append((f"{art.kennung}:", art.titel))
    return ergebnis
