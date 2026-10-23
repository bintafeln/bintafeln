from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.konten import rollen
from apps.kunden.forms import KundenEinstellungenForm, ZusatzfeldForm
from apps.kunden.models import KundenEinstellungen, Zusatzfeld


@rollen.rolle_erforderlich(rollen.ADMIN)
def einstellungen(request):
    form = KundenEinstellungenForm(request.POST or None, instance=KundenEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen des Kundenstamms gespeichert.")
        return redirect("kunden:einstellungen")
    return render(
        request,
        "kunden/einstellungen.html",
        {"form": form, "zusatzfelder": Zusatzfeld.objects.all()},
    )


@rollen.rolle_erforderlich(rollen.ADMIN)
def zusatzfeld_bearbeiten(request, pk=None):
    feld = get_object_or_404(Zusatzfeld, pk=pk) if pk else Zusatzfeld()
    form = ZusatzfeldForm(request.POST or None, instance=feld)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Zusatzfeld „{feld.bezeichnung}“ gespeichert.")
        return redirect("kunden:einstellungen")
    return render(request, "kunden/zusatzfeld.html", {"form": form, "feld": feld})
