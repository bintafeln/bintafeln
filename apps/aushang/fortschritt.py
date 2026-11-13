"""Aushang-Seite „Fortschritt der Ausgabe“ (ADR 0135): ein Monitor in der Verteilung zeigt groß,
wie weit die Ausgabe einer Ausgabestelle heute ist, z. B. „200 von 225“.

Läuft heute an der Ausgabestelle der Aufruf (Modul ``aufruf``, Tag gestartet), zählen die
aufgerufenen Nummern (wer schon vorher eingelassen wurde, zählt mit) von allen Nummern der
Aufrufliste. Sonst – ohne Aufruf oder vor dem Start – wie viele heute abgeholt haben von den
heute erwarteten Haushalten, wie der Fortschritt in der Kopfzeile am Einlass (ADR 0067). Nur
Zahlen, keine Namen oder Kundennummern.
"""

from django.template.loader import render_to_string
from django.utils import timezone

from apps.core import module

AUFGERUFEN, DA = "aufgerufen", "da"


def auswahl() -> list[tuple[str, str]]:
    from apps.kunden.models import Ausgabestelle

    return [(str(s.pk), s.name) for s in Ausgabestelle.objects.filter(aktiv=True).order_by("name")]


def _aufruf(stelle, heute) -> dict | None:
    if not module.aktiv("aufruf"):
        return None
    from apps.aufruf import ablauf

    tag = ablauf.tag_holen(stelle, heute)
    if tag is None or tag.gestartet_am is None:
        return None
    gruppen = tag.stand.get("gruppen", [])
    fertig = sum(len(g["aufgerufen"]) + len(g.get("eingelassen", [])) for g in gruppen)
    gesamt = fertig + sum(len(g["wartend"]) for g in gruppen)
    return {"fertig": fertig, "gesamt": gesamt, "art": AUFGERUFEN}


def zahlen(stelle, heute) -> dict | None:
    """{"fertig", "gesamt", "art"} für heute an der Stelle; None, wenn heute keine Ausgabe ist."""
    from apps.ausgabe import stelle as stellen

    ergebnis = _aufruf(stelle, heute)
    if ergebnis:
        return ergebnis
    f = stellen.fortschritt(stelle, heute)
    if f is None:
        return None
    return {"fertig": f.abgeholt, "gesamt": f.erwartet, "art": DA}


def folien(wert, von, bis) -> list[tuple[str, str, str, str]]:
    from apps.kunden.models import Ausgabestelle

    stelle = Ausgabestelle.objects.filter(pk=wert, aktiv=True).first() if str(wert).isdigit() \
        else None  # fmt: skip
    if stelle is None:
        return []
    heute = timezone.localdate()
    z = zahlen(stelle, heute)
    html = render_to_string("aushang/_fortschritt.html", {
        "z": z,
        "anteil": round(100 * z["fertig"] / z["gesamt"]) if z and z["gesamt"] else 0,
    })  # fmt: skip
    return [(f"Fortschritt {stelle.name}", html, "", f"Fortschritt {stelle.name}")]
