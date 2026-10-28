"""Seiten des Fahrdienstes für Aushang-Monitore (ADR 0080): je Monat eine Folie wie der
Fahrerplan, nur mit Namen. Mit PIN lassen sich am Monitor Ausfall, Ersatz und Gast für einen Tag
eintragen – mit denselben Regeln wie im Programm."""

import datetime as dt

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.core.auswahl import FAHRDIENST_AUSFALLGRUENDE
from apps.fahrdienst import plan
from apps.fahrdienst.models import Tour
from apps.konten import rollen


def auswahl() -> list[tuple[str, str]]:
    return []  # nur ein Fahrerplan


def folien(wert, von, bis) -> list[tuple[str, str, str, str]]:
    from apps.fahrdienst.views import MONATE

    ergebnis = []
    erster = von
    while erster <= bis:
        folgemonat = (erster.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        ende = min(bis, folgemonat - dt.timedelta(days=1))
        tage = plan.tage(plan.fahrtage(erster, ende))
        if tage:
            html = render_to_string("fahrdienst/_aushang.html", {
                "tage": tage, "touren": plan.touren(tage[0][0], tage[-1][0]),
                "heute": timezone.localdate(), "aushang": True,
            })  # fmt: skip
            monat = MONATE[erster.month - 1]
            ergebnis.append((f"Fahrerplan {monat} {erster.year}", html,
                             f"{reverse('fahrdienst:plan')}?monat={erster:%Y-%m}",
                             f"Fahrer {monat}"))  # fmt: skip
        erster = ende + dt.timedelta(days=1)
    return ergebnis


def _name(benutzer) -> str:
    return benutzer.get_full_name() or benutzer.get_username()


def _platz(teil: str):
    """``teil`` = "JJJJ-MM-TT|Tour|Platz"; nur Fahrtage ab heute."""
    try:
        datum_text, tour_pk, nr = teil.split("|")
        datum, nr = dt.date.fromisoformat(datum_text), int(nr)
        tour = Tour.objects.get(pk=int(tour_pk), aktiv=True)
    except (ValueError, Tour.DoesNotExist):
        return None
    if (datum < timezone.localdate() or not 1 <= nr <= tour.plaetze or not tour.faehrt_am(datum)
            or datum not in plan.fahrtage(datum, datum)):  # fmt: skip
        return None
    return plan.platz(datum, tour, nr)


def _frei(datum) -> list:
    springer, weitere = plan.verfuegbar(datum)
    return springer + weitere


def platz(teil: str) -> dict | None:
    p = _platz(teil)
    if p is None:
        return None
    status = {plan.OFFEN: "fällt aus, noch kein Ersatz", plan.UNBESETZT: "unbesetzt",
              plan.ERSETZT: "springt ein", plan.LEER: "frei (Platz für einen Gast)"}  # fmt: skip
    return {
        "titel": f"{p.datum:%d.%m.%Y} · {p.tour} · {p.name}",
        "wer": p.gast or (_name(p.wer) if p.wer else ""),
        "status": status.get(p.status, ""),
        "wer_konto": p.wer.pk if p.wer else None,
        "kann_ausfallen": p.wer is not None and not p.ausfall and not p.ersatz,
        "kann_einspringen": p.fehlt or p.status == plan.LEER,
        "gruende": FAHRDIENST_AUSFALLGRUENDE,
        "frei": [(b.pk, _name(b), b.pk) for b in _frei(p.datum)],
        "hat_ersatz": p.ersatz is not None,
        "recht": "fahrdienst.planen",
    }


def aendern(teil: str, daten, person, von: str, basis: str) -> str:
    p = _platz(teil)
    if p is None:
        raise ValueError("Diesen Platz gibt es nicht (mehr).")
    datum, aktion = p.datum, daten.get("aktion")
    planer = rollen.hat_recht(person, "fahrdienst.planen")
    if aktion in ("gast", "zuruecknehmen") and not planer:
        raise ValueError("Das darf nur, wer den Fahrdienst plant.")
    if aktion == "ausfall":
        if p.wer is None or p.ausfall or p.ersatz:
            raise ValueError("Hier kann niemand ausfallen.")
        if not planer and p.wer.pk != person.pk:
            raise ValueError("Austragen kann sich nur die Person selbst (oder wer den Fahrdienst "
                             "plant).")  # fmt: skip
        grund = daten.get("grund", "")
        if grund not in dict(FAHRDIENST_AUSFALLGRUENDE):
            raise ValueError("Bitte einen Grund wählen.")
        link = f"{basis}{reverse('fahrdienst:plan')}"
        plan.ausfall_melden(p.wer, datum, datum, grund, "", von, link)
        return (
            f"{_name(p.wer)} fällt am {datum:%d.%m.} aus. Die Fahrdienstleitung wird "
            "benachrichtigt."
        )
    if aktion == "ersatz":
        b = get_user_model().objects.filter(pk=daten.get("helfer") or 0, is_active=True).first()
        if b is None or b not in _frei(datum):
            raise ValueError("Diese Person kann an dem Tag nicht einspringen.")
        if not planer and (b.pk != person.pk or not (p.fehlt or p.status == plan.LEER)):
            raise ValueError("Einspringen kann man nur selbst und nur auf einem freien Platz (oder "
                             "wer den Fahrdienst plant).")  # fmt: skip
        plan.ersatz_eintragen(datum, p.tour, p.platz, b, von)
        return f"{_name(b)} springt am {datum:%d.%m.} ein ({p.tour})."
    if aktion == "gast":
        name = daten.get("gast", "").strip()
        if not name:
            raise ValueError("Bitte den Namen des Gasts eingeben.")
        plan.ersatz_eintragen(datum, p.tour, p.platz, None, von, gast=name)
        return f"Gast „{name[:100]}“ fährt am {datum:%d.%m.} mit ({p.tour})."
    if aktion == "zuruecknehmen" and p.ersatz:
        plan.ersatz_eintragen(datum, p.tour, p.platz, None, von)
        return f"Eintrag am {datum:%d.%m.} zurückgenommen ({p.tour})."
    raise ValueError("Unbekannte Aktion.")
