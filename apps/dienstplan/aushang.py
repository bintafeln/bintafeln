"""Seiten des Dienstplans für Aushang-Monitore (ADR 0080): je Ausgabetag der Stelle eine Folie
wie der Plan auf Papier, nur mit Namen. Mit PIN lassen sich am Monitor Ausfall, Ersatz und Gast
für einen Tag eintragen – mit denselben Regeln wie im Programm."""

import datetime as dt

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe.ampel import wochentage
from apps.core import ausfall as ausfallregeln
from apps.core.auswahl import AUSFALL_DAUER, FAHRDIENST_AUSFALLGRUENDE
from apps.dienstplan import plan
from apps.dienstplan.models import Aufgabe, Diensttag, Helfer
from apps.konten import rollen


def auswahl() -> list[tuple[str, str]]:
    return [(str(s.ausgabestelle_id), str(s)) for s in plan.stellen()]


def folien(wert, von, bis) -> list[tuple[str, str, str, str]]:
    from apps.dienstplan.views import TAGNAME

    stelle = plan.stellen().filter(ausgabestelle_id=wert).first() if str(wert).isdigit() else None
    if stelle is None:
        return []
    ergebnis = []
    von = max(von, timezone.localdate())  # vergangene Tage fallen weg
    for tag in wochentage(stelle.tage):
        daten, zeilen = plan.monat(stelle, tag, von, bis)
        if not daten or not zeilen:
            continue
        html = render_to_string("dienstplan/_aushang.html", {
            "daten": daten, "zeilen": zeilen, "heute": timezone.localdate(), "aushang": True,
            "diensttag": Diensttag.objects.filter(stelle=stelle, wochentag=tag).first(),
        })  # fmt: skip
        adresse = (f"{reverse('dienstplan:plan')}?stelle={stelle.ausgabestelle_id}&tag={tag}"
                   f"&monat={daten[0]:%Y-%m}")  # fmt: skip
        ergebnis.append((f"Dienstplan {stelle} · {TAGNAME[tag]}", html, adresse,
                         f"Ausgabe {stelle} {TAGNAME[tag]}"))  # fmt: skip
    return ergebnis


def _platz(teil: str):
    """``teil`` = "JJJJ-MM-TT|Aufgabe"; nur Ausgabetage ab heute."""
    try:
        datum_text, aufgabe_pk = teil.split("|")
        datum = dt.date.fromisoformat(datum_text)
        a = Aufgabe.objects.select_related("stelle__ausgabestelle").get(
            pk=int(aufgabe_pk), stelle__aktiv=True
        )
    except (ValueError, Aufgabe.DoesNotExist):
        return None
    if datum < timezone.localdate() or datum not in plan.ausgabetage(a.stelle, datum, datum,
                                                                      a.wochentag):  # fmt: skip
        return None
    return plan.platz(datum, a)


def platz(teil: str) -> dict | None:
    from apps.dienstplan.views import TAGNAME

    p = _platz(teil)
    if p is None:
        return None
    a = p.aufgabe
    status = {plan.OFFEN: "fällt aus, noch kein Ersatz", plan.UNBESETZT: "unbesetzt",
              plan.ERSETZT: "springt ein", plan.LEER: "frei"}.get(p.status, "")  # fmt: skip
    return {
        "titel": f"{TAGNAME[a.wochentag]} {p.datum:%d.%m.%Y} · {a.name} {a.zeit}",
        "wer": p.gast or (str(p.wer) if p.wer else ""),
        "status": _status(p, status),
        "wer_konto": p.wer.benutzer_id if p.wer else None,
        "kann_ausfallen": p.wer is not None and not p.ausfall and not p.ersatz,
        "kann_einspringen": p.fehlt or p.status == plan.LEER,
        "gruende": FAHRDIENST_AUSFALLGRUENDE,
        "dauer": AUSFALL_DAUER,
        "datum": p.datum.isoformat(),
        "kann_gesund": p.ausfall is not None and p.ersatz is None and not p.ausfall.gesund_ab,
        "frei": [(h.pk, str(h), h.benutzer_id) for h in plan.verfuegbar(p.datum)],
        "hat_ersatz": p.ersatz is not None,
        "recht": "dienstplan.planen",
    }


def _status(p, status) -> str:
    if p.ausfall and p.ausfall.gesund_ab and p.datum >= p.ausfall.gesund_ab and not p.ersatz:
        return "wieder da, der Platz bleibt aber frei (noch kein Ersatz)"
    return status


def aendern(teil: str, daten, person, von: str, basis: str) -> str:
    p = _platz(teil)
    if p is None:
        raise ValueError("Diesen Platz gibt es nicht (mehr).")
    a, datum, aktion = p.aufgabe, p.datum, daten.get("aktion")
    planer = rollen.hat_recht(person, "dienstplan.planen")
    if aktion in ("gast", "zuruecknehmen") and not planer:
        raise ValueError("Das darf nur, wer den Dienstplan plant.")
    if aktion == "ausfall":
        if p.wer is None or p.ausfall or p.ersatz:
            raise ValueError("Hier kann niemand ausfallen.")
        if not planer and p.wer.benutzer_id != person.pk:
            raise ValueError("Austragen kann sich nur die Person selbst (oder wer den Dienstplan "
                             "plant).")  # fmt: skip
        grund = daten.get("grund", "")
        if grund not in dict(FAHRDIENST_AUSFALLGRUENDE):
            raise ValueError("Bitte einen Grund wählen.")
        bis = ausfallregeln.bis_berechnen(datum, daten.get("dauer", ""), daten.get("bis", ""))
        link = f"{basis}{reverse('dienstplan:plan')}"
        plan.ausfall_melden(p.wer, datum, bis, grund, "", von, link)
        zeit = f"am {datum:%d.%m.}" if bis == datum else f"vom {datum:%d.%m.} bis {bis:%d.%m.%Y}"
        return f"{p.wer} fällt {zeit} aus. Die Teamleitung wird benachrichtigt."
    if aktion == "gesund":
        if p.ausfall is None or p.ersatz or p.ausfall.gesund_ab:
            raise ValueError("Hier ist kein Ausfall, der noch läuft.")
        if not planer and p.wer.benutzer_id != person.pk:
            raise ValueError("Gesund melden kann sich nur die Person selbst (oder wer den "
                             "Dienstplan plant).")  # fmt: skip
        plan.gesund_melden(p.ausfall, timezone.localdate(), f"{basis}{reverse('dienstplan:plan')}")
        return (f"{p.wer} ist wieder da und kann einspringen. Die eigenen Dienste bleiben frei "
                "bzw. beim Ersatz: Bitte dort wieder eintragen, wo noch jemand fehlt.")  # fmt: skip
    if aktion == "ersatz":
        h = Helfer.objects.filter(pk=daten.get("helfer") or 0, aktiv=True).first()
        if h is None or h not in plan.verfuegbar(datum):
            raise ValueError("Diese Person kann an dem Tag nicht einspringen.")
        if not planer and (h.benutzer_id != person.pk or not (p.fehlt or p.status == plan.LEER)):
            raise ValueError("Einspringen kann man nur selbst und nur auf einem freien Platz (oder "
                             "wer den Dienstplan plant).")  # fmt: skip
        plan.ersatz_eintragen(datum, a, h, von)
        return f"{h} springt am {datum:%d.%m.} ein ({a.name})."
    if aktion == "gast":
        name = daten.get("gast", "").strip()
        if not name:
            raise ValueError("Bitte den Namen des Gasts eingeben.")
        plan.ersatz_eintragen(datum, a, None, von, gast=name)
        return f"Gast „{name[:100]}“ hilft am {datum:%d.%m.} mit ({a.name})."
    if aktion == "zuruecknehmen" and p.ersatz:
        plan.ersatz_eintragen(datum, a, None, von)
        return f"Eintrag am {datum:%d.%m.} zurückgenommen ({a.name})."
    raise ValueError("Unbekannte Aktion.")
