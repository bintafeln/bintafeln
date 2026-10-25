"""Sicherungen in der Oberfläche: Sofort-Sicherung und Sicherungsaufträge (ADR 0042).

Die Oberfläche speichert nur Aufträge und Anforderungen; ausgeführt werden sie vom Dienst
"backup", der die Tabelle alle 15 Sekunden liest und den Stand zurückschreibt.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import sicherung
from apps.core.forms import SicherungsAuftragForm
from apps.core.models import SicherungsAuftrag, SicherungsDienst
from apps.konten import rollen
from apps.konten.views import nicht_in_demo


def _kontext():
    auftraege = list(SicherungsAuftrag.objects.all())
    return {
        "auftraege": auftraege,
        "dienst": sicherung.dienst_status(),
        # Solange etwas läuft oder angefordert ist, lädt sich die Liste alle 5 Sekunden neu
        "beschaeftigt": any(a.laeuft_seit or a.angefordert_am for a in auftraege),
    }


@never_cache
@rollen.recht_erforderlich("system.sicherung")
def seite(request):
    vorlage = "core/_sicherungen_liste.html" if request.headers.get("HX-Request") else (
        "core/sicherungen.html")  # fmt: skip
    return render(request, vorlage, _kontext())


@never_cache
@rollen.recht_erforderlich("system.sicherung")
@nicht_in_demo
def auftrag(request, pk=None):
    a = get_object_or_404(SicherungsAuftrag, pk=pk) if pk else SicherungsAuftrag(uhrzeit="22:00")
    form = SicherungsAuftragForm(
        request.POST or None, instance=a, ziele=SicherungsDienst.laden().ziele_liste()
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Sicherungsauftrag „{a.name}“ gespeichert.")
        return redirect("core:sicherungen")
    return render(request, "core/sicherungsauftrag.html", {"form": form, "a": a})


@require_POST
@rollen.recht_erforderlich("system.sicherung")
@nicht_in_demo
def loeschen(request, pk):
    a = get_object_or_404(SicherungsAuftrag, pk=pk, standard=False)
    a.delete()
    messages.success(request, f"Sicherungsauftrag „{a.name}“ gelöscht. Vorhandene Sicherungen am "
                              "Ziel bleiben erhalten.")  # fmt: skip
    return redirect("core:sicherungen")


@require_POST
@rollen.recht_erforderlich("system.sicherung")
@nicht_in_demo
def jetzt(request, pk):
    a = get_object_or_404(SicherungsAuftrag, pk=pk)
    sicherung.anfordern(a, request.user.get_username())
    messages.success(request, f"Sicherung „{a.name}“ angefordert. Sie startet in wenigen Sekunden.")
    return redirect("core:sicherungen")
