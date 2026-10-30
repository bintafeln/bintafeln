"""bintafeln-Verzeichnis (ADR 0089): freiwillige Meldung der Tafel und, beim Herausgeber,
Empfang und Liste der gemeldeten Tafeln. Logik in ``apps/core/verzeichnis.py``."""

import json

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core import verzeichnis
from apps.core.models import VerzeichnisEintrag, VerzeichnisMeldung
from apps.konten import rollen
from apps.konten.views import nicht_in_demo

GROESSE = 4096  # Bytes je Meldung
JE_STUNDE = 30  # Meldungen je Absender-Adresse


def _ip(request) -> str:
    """Hinter Caddy steht die Adresse als erster Eintrag in X-Forwarded-For."""
    weitergeleitet = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return weitergeleitet.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


class MeldungForm(forms.ModelForm):
    class Meta:
        model = VerzeichnisMeldung
        fields = ["aktiv", "kontakt"]


@never_cache
@rollen.recht_erforderlich("einstellungen.tafel")
@nicht_in_demo
def einstellung(request):
    m = VerzeichnisMeldung.laden()
    vorher = m.aktiv
    form = MeldungForm(request.POST or None, instance=m)
    if request.method == "POST" and form.is_valid():
        m = form.save()
        if m.aktiv and (not vorher or "jetzt" in request.POST):
            if verzeichnis.melden():
                messages.success(request, "Die Tafel ist im bintafeln-Verzeichnis gemeldet.")
            else:
                messages.error(request, "Gespeichert, aber die Meldung hat nicht geklappt: "
                               f"{VerzeichnisMeldung.laden().fehler} bintafeln versucht es "
                               "später von selbst noch einmal.")  # fmt: skip
        elif vorher and not m.aktiv:
            if verzeichnis.abmelden():
                messages.success(request, "Die Tafel ist aus dem bintafeln-Verzeichnis entfernt.")
            else:
                messages.error(request, "Ausgeschaltet, aber das Verzeichnis war nicht "
                               "erreichbar; der Eintrag dort bleibt vorerst.")  # fmt: skip
        else:
            messages.success(request, "Gespeichert.")
        return redirect("core:verzeichnis")
    return render(request, "core/verzeichnis.html", {
        "form": form, "m": VerzeichnisMeldung.laden(), "angaben": verzeichnis.angaben(),
        "url": settings.VERZEICHNIS_URL,
    })  # fmt: skip


@csrf_exempt
@require_POST
def melden(request):
    """Nimmt Meldungen anderer Tafeln an – nur beim Herausgeber eingeschaltet."""
    if not settings.VERZEICHNIS_EMPFANG:
        raise Http404
    schluessel = f"verzeichnis-{_ip(request)}"
    anzahl = cache.get(schluessel, 0)
    if anzahl >= JE_STUNDE:
        return JsonResponse({"fehler": "zu viele Meldungen"}, status=429)
    cache.set(schluessel, anzahl + 1, 3600)
    if len(request.body) > GROESSE:
        return JsonResponse({"fehler": "zu groß"}, status=413)
    try:
        ergebnis = verzeichnis.annehmen(json.loads(request.body or b"{}"))
    except ValueError as e:
        return JsonResponse({"fehler": str(e) or "ungültig"}, status=400)
    return JsonResponse({"ergebnis": ergebnis})


@never_cache
@rollen.recht_erforderlich("einstellungen.tafel")
def liste(request):
    if not settings.VERZEICHNIS_EMPFANG:
        raise Http404
    still = timezone.now() - 2 * verzeichnis.ABSTAND
    return render(request, "core/verzeichnis_liste.html", {
        "eintraege": VerzeichnisEintrag.objects.all(), "still_seit": still,
    })  # fmt: skip
