"""Öffentliche Anzeige der aufgerufenen Nummern für die Homepage der Tafel (ADR 0181)."""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.aufruf import homepage
from apps.aufruf.models import AufrufEinstellungen, neuer_schluessel
from apps.konten import rollen
from apps.konten.views import nicht_in_demo


@require_GET
@xframe_options_exempt
def anzeige(request, schluessel):
    e = homepage.einstellungen(schluessel)
    if e is None:
        raise Http404
    teil = request.GET.get("teil") == "1"  # nur der Kasten, zum Nachladen
    stand = homepage.stand(e)
    naechste = stand["naechste"]
    jetzt = timezone.now()
    antwort = render(
        request,
        "aufruf/_homepage_stand.html" if teil else "aufruf/homepage.html",
        {
            "stand": stand,
            "stelle": e.ausgabestelle,
            "neu_laden": homepage.NEU_LADEN,
            "heute": naechste is not None and naechste["tag"] == timezone.localdate(),
            "bis_dahin": homepage.countdown(naechste and naechste["ziel"], jetzt),
        },
    )
    # Einbetten nur von der eingetragenen Homepage; diese Angabe geht in Browsern vor
    # X-Frame-Options, das der Proxy sonst auf DENY setzt.
    antwort["Content-Security-Policy"] = f"frame-ancestors {homepage.einbetten_erlaubt(e)}"
    antwort["Cache-Control"] = f"public, max-age={homepage.SEKUNDEN}"
    antwort["Referrer-Policy"] = "no-referrer"
    antwort["X-Robots-Tag"] = "noindex, nofollow"
    return antwort


@require_POST
@rollen.recht_erforderlich("einstellungen.aufruf")
@nicht_in_demo
def schluessel_neu(request, pk):
    """Neuer Link für die Homepage-Anzeige; der alte zeigt danach nichts mehr."""
    e = get_object_or_404(AufrufEinstellungen, ausgabestelle_id=pk)
    e.homepage_schluessel = neuer_schluessel()
    e.save()
    messages.success(request, f"Neuer Link für die Homepage von „{e.ausgabestelle}“ erzeugt. "
                     "Bitte auf der Homepage den neuen Link eintragen.")  # fmt: skip
    return redirect("aufruf:einstellungen")
