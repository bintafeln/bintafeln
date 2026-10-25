"""Korrekturwünsche vom Einlass entscheiden (ADR 0035)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.ausgabe import korrekturen
from apps.ausgabe.models import Korrekturwunsch
from apps.konten import rollen

entscheider = rollen.recht_erforderlich("korrekturen.entscheiden")


@entscheider
def liste(request):
    alle = Korrekturwunsch.objects.all()
    return render(
        request,
        "ausgabe/korrekturen.html",
        {
            "offen": alle.filter(status=Korrekturwunsch.Status.OFFEN).order_by("erstellt_am"),
            "entschieden": alle.exclude(status=Korrekturwunsch.Status.OFFEN)[:50],
        },
    )


@require_POST
@entscheider
def entscheiden(request, pk):
    k = get_object_or_404(Korrekturwunsch, pk=pk)
    annehmen = request.POST.get("entscheidung") == "zuruecknehmen"
    try:
        ergebnis = korrekturen.entscheiden(
            k, annehmen=annehmen, von=request.user.get_username(),
            antwort=request.POST.get("antwort", "").strip(),
        )  # fmt: skip
    except korrekturen.KorrekturFehler as fehler:
        messages.error(request, str(fehler))
    else:
        messages.success(request, f"Korrekturwunsch für Kunde {k.kundennummer}: {ergebnis}.")
    return redirect("ausgabe:korrekturen")
