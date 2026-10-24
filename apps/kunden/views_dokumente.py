"""Dokumente zu Haushalten (ADR 0030): nur Admin und Büro, verschlüsselt, Abruf protokolliert."""

from auditlog.signals import accessed
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import privatdateien
from apps.konten import rollen
from apps.kunden.forms_bearbeiten import HaushaltDokumentForm
from apps.kunden.models import Haushalt, HaushaltDokument, Zugriff

buero = rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
MAX_MB = 10


def kontext(kundennummer: str) -> dict:
    """Für das Template kunden/_dokumente.html."""
    return {
        "dokumente": HaushaltDokument.objects.filter(kundennummer=kundennummer).select_related(
            "art"
        ),
        "dokument_form": HaushaltDokumentForm(),
    }


@require_POST
@buero
def hochladen(request, kundennummer):
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    form = HaushaltDokumentForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Nicht gespeichert: Dokumentart und Datei sind Pflicht.")
        return redirect("kunden:haushalt", kundennummer=h.kundennummer)
    datei = form.cleaned_data["datei"]
    try:
        name = privatdateien.speichern(HaushaltDokument.ORDNER, datei, max_mb=MAX_MB)
    except privatdateien.DateiFehler as fehler:
        messages.error(request, str(fehler))
        return redirect("kunden:haushalt", kundennummer=h.kundennummer)
    d = form.instance
    d.kundennummer = h.kundennummer
    d.titel = d.titel.strip() or str(d.art)
    d.datei, d.typ, d.groesse = name, datei.content_type, datei.size
    d.hochgeladen_von = request.user.get_username()[:150]
    d.save()
    messages.success(
        request, f"Dokument verschlüsselt gespeichert, wird am {d.loeschen_am:%d.%m.%Y} gelöscht."
    )
    return redirect("kunden:haushalt", kundennummer=h.kundennummer)


@never_cache
@buero
def ansehen(request, pk):
    d = get_object_or_404(HaushaltDokument, pk=pk)
    inhalt = privatdateien.lesen(HaushaltDokument.ORDNER, d.datei)
    if inhalt is None:
        raise Http404
    accessed.send(sender=HaushaltDokument, instance=d)  # Abruf im Änderungsprotokoll
    Zugriff.objects.create(
        benutzer=request.user,
        benutzername=request.user.get_username(),
        kundennummer=d.kundennummer,
    )
    antwort = HttpResponse(inhalt, content_type=d.typ)
    antwort["Content-Disposition"] = "inline"
    return antwort


@require_POST
@buero
def loeschen(request, pk):
    d = get_object_or_404(HaushaltDokument, pk=pk)
    d.loeschen()
    messages.success(request, f"Dokument „{d.titel}“ gelöscht.")
    return redirect("kunden:haushalt", kundennummer=d.kundennummer)
