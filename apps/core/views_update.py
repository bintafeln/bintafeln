"""Seite „Einstellungen → Update“ (ADR 0043)."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import update
from apps.core.models import SicherungsDienst
from apps.konten import rollen
from apps.konten.views import nicht_in_demo


@never_cache
@rollen.recht_erforderlich("system.update")
def seite(request):
    stand = update.stand()
    kontext = {
        "s": stand,
        "neuere": [v for v in stand.versionen if stand.ist_neuer(v)],
        "aeltere": [
            v for v in stand.versionen if not stand.ist_neuer(v) and v.name != stand.installiert
        ],  # fmt: skip
        "schluessel_ok": SicherungsDienst.laden().schluessel_ok,
    }
    vorlage = "core/_update_stand.html" if request.headers.get("HX-Request") else "core/update.html"
    return render(request, vorlage, kontext)


@require_POST
@rollen.recht_erforderlich("system.update")
@nicht_in_demo
def starten(request):
    version = request.POST.get("version", "")
    if request.POST.get("bestaetigt") != "ja":
        messages.error(request, "Bitte das Update ausdrücklich bestätigen.")
        return redirect("core:update")
    try:
        update.anfordern(version, request.user.get_username())
    except update.UpdateFehler as fehler:
        messages.error(request, str(fehler))
    else:
        messages.success(
            request,
            f"Update auf {version} angefordert. Es startet in wenigen Sekunden; bintafeln ist "
            "dabei kurz nicht erreichbar.",
        )
    return redirect("core:update")


@require_POST
@rollen.recht_erforderlich("system.update")
def abrufen(request):
    update.jetzt_abrufen()
    messages.success(request, "Es wird nach neuen Versionen gesucht.")
    return redirect("core:update")
