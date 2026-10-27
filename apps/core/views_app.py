"""App-Symbol und Web-App-Manifest (öffentlich, auch vor der Anmeldung).

Hat die Tafel ein eigenes App-Symbol hochgeladen, liefert bintafeln es in der gewünschten Größe;
sonst das Symbol von bintafeln aus ``static/img``.
"""

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control

from apps.core import bilder
from apps.core.models import TafelEinstellungen
from bintafeln import programm


@cache_control(public=True, max_age=3600)
def symbol(request, groesse: int):
    if groesse not in bilder.SYMBOL_GROESSEN:
        raise Http404
    tafel = TafelEinstellungen.laden()
    if tafel.app_symbol:
        try:
            with tafel.app_symbol.open("rb") as datei:
                return HttpResponse(bilder.symbol_in_groesse(datei, groesse),
                                    content_type="image/png")  # fmt: skip
        except (OSError, ValueError):
            pass  # Datei fehlt oder ist kaputt: Symbol von bintafeln
    return redirect(static(f"img/bintafeln-{groesse}.png"))


@cache_control(public=True, max_age=3600)
def manifest(request):
    """Damit Handy und Tablet bintafeln mit Namen und Symbol auf den Startbildschirm legen."""
    tafel = TafelEinstellungen.laden()
    name = tafel.name or programm.NAME
    return JsonResponse({
        "name": name,
        "short_name": name[:12],
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "lang": "de",
        "theme_color": tafel.farbe,
        "background_color": "#ffffff",
        "icons": [
            {"src": reverse("core:app_symbol", args=[g]), "sizes": f"{g}x{g}", "type": "image/png"}
            for g in (192, 512)
        ],
    }, content_type="application/manifest+json")  # fmt: skip
