"""Seiten des Fahrdienstes für Aushang-Monitore (ADR 0080): je Monat eine Folie wie der
Fahrerplan, nur mit Namen. Mit PIN lassen sich am Monitor Ausfall, Ersatz und Gast für einen Tag
eintragen – mit denselben Regeln wie im Programm."""

import datetime as dt

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.adressen.models import Adresse
from apps.core import ausfall as ausfallregeln
from apps.core.auswahl import AUSFALL_DAUER, FAHRDIENST_AUSFALLGRUENDE
from apps.fahrdienst import plan
from apps.fahrdienst.models import Tour
from apps.konten import rollen


def auswahl() -> list[tuple[str, str]]:
    return []  # nur ein Fahrerplan


def _folie(von, bis) -> str | None:
    tage = plan.tage(plan.fahrtage(von, bis))
    if not tage:
        return None
    return render_to_string("fahrdienst/_aushang.html", {
        "tage": tage, "touren": plan.touren(tage[0][0], tage[-1][0]),
        "heute": timezone.localdate(), "aushang": True,
    })  # fmt: skip


def folien(wert, von, bis) -> list[tuple[str, str, str, str]]:
    """Ganze Monate: je Monat eine Folie, ohne vergangene Tage. Die nächsten Wochen ab heute:
    eine Folie für alles."""
    from apps.fahrdienst.views import MONATE

    if von.day != 1 or (bis + dt.timedelta(days=1)).day != 1:
        html = _folie(von, bis)
        if not html:
            return []
        return [(f"Fahrerplan {von:%d.%m.} bis {bis:%d.%m.%Y}", html,
                 f"{reverse('fahrdienst:plan')}?monat={von:%Y-%m}", "Fahrer")]  # fmt: skip
    ergebnis = []
    erster = von
    while erster <= bis:
        folgemonat = (erster.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        ende = min(bis, folgemonat - dt.timedelta(days=1))
        html = _folie(max(erster, timezone.localdate()), ende)  # vergangene Tage fallen weg
        if html:
            monat = MONATE[erster.month - 1]
            ergebnis.append((f"Fahrerplan {monat} {erster.year}", html,
                             f"{reverse('fahrdienst:plan')}?monat={erster:%Y-%m}",
                             f"Fahrer {monat}"))  # fmt: skip
        erster = ende + dt.timedelta(days=1)
    return ergebnis


def _name(person) -> str:
    return person.name


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


def _frei(datum, nur_fahrer: bool = False) -> list:
    springer, weitere = plan.verfuegbar(datum, nur_fahrer=nur_fahrer)
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
        "status": _status(p, status.get(p.status, "")),
        "wer_konto": p.wer.konto_id if p.wer else None,
        "kann_ausfallen": p.wer is not None and not p.ausfall,  # auch wer eingesprungen ist
        "kann_einspringen": p.fehlt or p.status == plan.LEER,
        "gruende": FAHRDIENST_AUSFALLGRUENDE,
        "dauer": AUSFALL_DAUER,
        "datum": p.datum.isoformat(),
        "kann_gesund": p.ausfall is not None and not p.ausfall.gesund_ab,
        "frei": [(b.pk, _name(b), b.konto_id) for b in _frei(p.datum, nur_fahrer=p.platz == 1)],
        "hat_ersatz": p.ersatz is not None,
        "recht": "fahrdienst.planen",
    }


def _status(p, status) -> str:
    if p.ausfall and p.ausfall.gesund_ab and p.datum >= p.ausfall.gesund_ab:
        return "wieder da, der Platz bleibt aber frei (noch kein Ersatz)"
    return status


def aendern(teil: str, daten, person, von: str, basis: str) -> str:
    p = _platz(teil)
    if p is None:
        raise ValueError("Diesen Platz gibt es nicht (mehr).")
    datum, aktion = p.datum, daten.get("aktion")
    planer = rollen.hat_recht(person, "fahrdienst.planen")
    if aktion in ("gast", "zuruecknehmen") and not planer:
        raise ValueError("Das darf nur, wer den Fahrdienst plant.")
    if aktion == "ausfall":
        if p.wer is None or p.ausfall:
            raise ValueError("Hier kann niemand ausfallen.")
        if not planer and p.wer.konto_id != person.pk:
            raise ValueError("Austragen kann sich nur die Person selbst (oder wer den Fahrdienst "
                             "plant).")  # fmt: skip
        grund = daten.get("grund", "")
        if grund not in dict(FAHRDIENST_AUSFALLGRUENDE):
            raise ValueError("Bitte einen Grund wählen.")
        bis = ausfallregeln.bis_berechnen(datum, daten.get("dauer", ""), daten.get("bis", ""))
        link = f"{basis}{reverse('fahrdienst:plan')}"
        plan.ausfall_melden(p.wer, datum, bis, grund, "", von, link)
        zeit = f"am {datum:%d.%m.}" if bis == datum else f"vom {datum:%d.%m.} bis {bis:%d.%m.%Y}"
        return f"{_name(p.wer)} fällt {zeit} aus. Die Fahrdienstleitung wird benachrichtigt."
    if aktion == "gesund":
        if p.ausfall is None or p.ausfall.gesund_ab:
            raise ValueError("Hier ist kein Ausfall, der noch läuft.")
        if not planer and p.wer.konto_id != person.pk:
            raise ValueError("Gesund melden kann sich nur die Person selbst (oder wer den "
                             "Fahrdienst plant).")  # fmt: skip
        plan.gesund_melden(p.ausfall, timezone.localdate(), f"{basis}{reverse('fahrdienst:plan')}")
        return (f"{_name(p.wer)} ist wieder da und kann einspringen. Die eigenen Touren "
                "bleiben frei bzw. beim Ersatz: Bitte dort wieder eintragen, wo noch jemand "
                "fehlt.")  # fmt: skip
    if aktion == "ersatz":
        b = Adresse.objects.filter(pk=daten.get("helfer") or 0).first()
        if b is None or b not in _frei(datum, nur_fahrer=p.platz == 1):
            raise ValueError("Diese Person kann an dem Tag nicht einspringen.")
        if not planer and (b.konto_id != person.pk or not (p.fehlt or p.status == plan.LEER)):
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
