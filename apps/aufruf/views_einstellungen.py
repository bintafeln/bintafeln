"""Einstellungen des Aufrufs (Recht ``einstellungen.aufruf``): Ausgabestellen und Monitor-Infos."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.aufruf.forms import EinstellungenForm, InfoForm
from apps.aufruf.models import AufrufEinstellungen, AufrufInfo, neuer_schluessel
from apps.konten import rollen
from apps.konten.views import nicht_in_demo
from apps.kunden.models import Ausgabestelle

einstellen = rollen.recht_erforderlich("einstellungen.aufruf")


@never_cache
@einstellen
def einstellungen(request):
    stellen = [(s, AufrufEinstellungen.laden(s))
               for s in Ausgabestelle.objects.filter(aktiv=True)]  # fmt: skip
    return render(request, "aufruf/einstellungen.html", {
        "stellen": stellen, "infos": AufrufInfo.objects.prefetch_related("ausgabestellen"),
    })  # fmt: skip


@never_cache
@einstellen
def stelle(request, pk):
    s = get_object_or_404(Ausgabestelle, pk=pk)
    form = EinstellungenForm(request.POST or None, instance=AufrufEinstellungen.laden(s))
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Aufruf für „{s}“ gespeichert.")
        return redirect("aufruf:einstellungen")
    return render(request, "aufruf/einstellungen_stelle.html", {"form": form, "s": s})


@require_POST
@einstellen
@nicht_in_demo
def schluessel_neu(request, pk):
    e = AufrufEinstellungen.laden(get_object_or_404(Ausgabestelle, pk=pk))
    e.schluessel = neuer_schluessel()
    e.save()
    messages.success(request, f"Neue Links für „{e.ausgabestelle}“ erzeugt. Die alten Links "
                     "funktionieren nicht mehr – bitte an den Geräten neu öffnen.")  # fmt: skip
    return redirect("aufruf:einstellungen")


@never_cache
@einstellen
def info(request, pk=None):
    instanz = get_object_or_404(AufrufInfo, pk=pk) if pk else AufrufInfo()
    form = InfoForm(request.POST or None, request.FILES or None, instance=instanz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Info „{form.instance}“ gespeichert.")
        return redirect("aufruf:einstellungen")
    return render(request, "aufruf/info.html", {"form": form, "info": instanz if pk else None})


@require_POST
@einstellen
def info_loeschen(request, pk):
    i = get_object_or_404(AufrufInfo, pk=pk)
    if i.datei:
        i.datei.delete(save=False)
    i.delete()
    messages.success(request, f"Info „{i}“ gelöscht.")
    return redirect("aufruf:einstellungen")
