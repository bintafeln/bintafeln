"""Welche Links jemand sieht (ADR 0057)."""

from apps.konten import rollen
from apps.links.models import Link


def sichtbar(benutzer) -> list[tuple[str, list[Link]]]:
    """[(Gruppe, Links)] in fester Reihenfolge; Links ohne Gruppe zuerst."""
    meine = rollen.rollen_von(benutzer)
    admin = rollen.ADMIN in meine
    gruppen: dict = {}
    links = Link.objects.filter(aktiv=True).select_related("gruppe").prefetch_related("rollen")
    for link in sorted(links, key=lambda x: (x.gruppe is not None,
                                             x.gruppe.reihenfolge if x.gruppe else 0,
                                             x.gruppe.titel if x.gruppe else "",
                                             x.reihenfolge, x.titel)):  # fmt: skip
        fuer = {g.name for g in link.rollen.all()}
        if fuer and not admin and not fuer & meine:
            continue
        gruppen.setdefault(link.gruppe.titel if link.gruppe else "", []).append(link)
    return list(gruppen.items())


def startseite(request) -> str:
    from django.template.loader import render_to_string

    gruppen = sichtbar(request.user)
    if not gruppen:
        return ""
    return render_to_string("links/_kacheln.html", {"gruppen": gruppen}, request=request)
