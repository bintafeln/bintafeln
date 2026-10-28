"""Was ein Aushang-Monitor zeigt (ADR 0080): die Folien der Seiten im gewählten Zeitraum."""

import datetime as dt

from apps.aushang.models import Aushang, AushangSeite
from apps.core import module


def zeitraum(heute: dt.date, monate: int, wochen: int = 0) -> tuple[dt.date, dt.date]:
    """Der ganze Monat (bzw. dieser und der nächste): wie der Plan auf Papier; mit zwei Monaten
    ist am Monatsende schon der nächste zu sehen. Mit ``wochen`` stattdessen die nächsten Wochen
    ab heute, ohne vergangene Tage."""
    if wochen:
        return heute, heute + dt.timedelta(days=7 * wochen - 1)
    erster = heute.replace(day=1)
    ende = erster
    for _ in range(monate):
        ende = (ende + dt.timedelta(days=32)).replace(day=1)
    return erster, ende - dt.timedelta(days=1)


def folien(aushang: Aushang, heute: dt.date) -> list[tuple[str, str, str, str]]:
    """[(titel, html, adresse, kurz)] aller Seiten; Seiten ausgeschalteter Module fallen weg."""
    arten = module.aushangseiten()
    ergebnis = []
    for seite in aushang.seiten.all():
        art = arten.get(seite.art)
        if art:
            ergebnis += art.folien(seite.wert, *zeitraum(heute, seite.monate, seite.wochen))
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


def _art(kennung: str):
    art_name, _, teil = (kennung or "").partition("|")
    art = module.aushangseiten().get(art_name)
    return (art, teil) if art and art.platz and art.aendern else (None, teil)


def platz_dialog(kennung: str) -> dict | None:
    """Was der Dialog am Monitor zu einem Platz anbietet. Zur Wahl stehen nur Personen mit PIN:
    die Person auf dem Platz (sich austragen), wer frei ist (einspringen) und wer planen darf."""
    from django.contrib.auth import get_user_model

    from apps.aushang import pin
    from apps.konten import rollen

    art, teil = _art(kennung)
    info = art.platz(teil) if art else None
    if info is None:
        return None
    pins = pin.mit_pin()
    konten = get_user_model().objects.filter(pk__in=pins).order_by("first_name", "last_name")
    return {
        **info,
        "kennung": kennung,
        "selbst_aus": info["kann_ausfallen"] and info["wer_konto"] in pins,
        "einspringer": [
            (f"{wert}:{konto}", name) for wert, name, konto in info["frei"] if konto in pins
        ]
        if info["kann_einspringen"]
        else [],  # fmt: skip
        "planer": [(b.pk, str(b)) for b in konten if rollen.hat_recht(b, info["recht"])],
    }


def aendern(aushang: Aushang, kennung: str, daten, basis: str) -> str:
    """Eine Änderung am Monitor: Person per PIN bestätigen, dann prüft das Modul, was sie darf.
    Im Plan steht „<Konto> am Monitor …“, im Änderungsprotokoll die Person selbst."""
    from auditlog.context import set_actor

    from apps.aushang import pin

    art, teil = _art(kennung)
    if art is None or art.platz(teil) is None:
        raise ValueError("Diesen Platz gibt es nicht (mehr).")
    werte = {k: daten.get(k, "") for k in ("aktion", "grund", "helfer", "gast")}
    person_wert = daten.get("person", "")
    if werte["aktion"] == "einspringen":  # die Wahl „Helfer:Konto“ ist zugleich die Person
        werte["helfer"], _, person_wert = daten.get("einspringer", "").partition(":")
        werte["aktion"] = "ersatz"
    person = pin.pruefen(person_wert, daten.get("pin", ""))
    von = f"{person.get_username()} am Monitor „{aushang.name}“"[:150]
    with set_actor(person):
        return art.aendern(teil, werte, person, von, basis)
