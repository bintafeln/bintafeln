"""Sammel-Verlängerung der Ausweise (ADR 0068); Regeln in ``apps/kunden/verlaengerung.py``."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.konten import rollen
from apps.kunden import verlaengerung
from apps.kunden.models import KundenEinstellungen

MONATE = [3, 6, 12, 24]


def _monate(wert, vorgabe: int) -> int:
    return int(wert) if str(wert).isdigit() and 1 <= int(wert) <= 60 else vorgabe


@never_cache
@rollen.recht_erforderlich("kunden.bearbeiten")
def verlaengern(request):
    e = KundenEinstellungen.laden()
    heute = timezone.localdate()
    daten = request.POST if request.method == "POST" else request.GET
    monate = _monate(daten.get("monate", ""), e.ausweis_gueltig_monate)
    if request.method == "POST":
        v, p = verlaengerung.ausfuehren(
            request.user, heute, monate,
            set(request.POST.getlist("verlaengern")), set(request.POST.getlist("ablehnen")),
            an_stelle=bool(request.POST.get("an_stelle")),
        )  # fmt: skip
        if v or p:
            text = f"{v} Ausweis{'e' if v != 1 else ''} verlängert"
            if p:
                text += f", {p} nicht verlängert"
            messages.success(request, text + ".")
        else:
            messages.info(request, "Nichts ausgewählt.")
        return redirect(f"{reverse('kunden:verlaengern')}?monate={monate}")
    liste = verlaengerung.gemeldete(request.user, heute, monate)
    return render(request, "kunden/verlaengern.html", {
        "liste": liste,
        "monate": monate,
        "monate_auswahl": sorted({*MONATE, e.ausweis_gueltig_monate}),
        "einstellungen": e,
        "ablehnung": e.verlaengern_ablehnung,
        "pause_text": verlaengerung.pause_text(e.verlaengern_sonst_pausieren_monate),
        "pause": e.verlaengern_sonst_pausieren_monate,
        "anzahl": {k: sum(1 for p in liste if p.ergebnis == k)
                   for k in (verlaengerung.OK, verlaengerung.NEIN, verlaengerung.UNKLAR)},
        "bedingungen": verlaengerung.bedingungen_text(e),
        "regel": e.get_verlaengern_regel_display(),
    })  # fmt: skip
