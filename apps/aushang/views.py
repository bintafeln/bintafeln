"""Aushang-Monitore einrichten und anzeigen (ADR 0080); was angezeigt wird, in ``anzeige.py``."""

from django.contrib import messages
from django.db.models import Max
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.aushang import anzeige as inhalt
from apps.aushang.forms import AushangForm, NeuForm, SeiteForm
from apps.aushang.models import Aushang, AushangSeite, neuer_schluessel
from apps.core import module, papierkorb
from apps.konten import rollen

einrichten = rollen.recht_erforderlich("aushang.einrichten")


def _link(request, aushang) -> str:
    return request.build_absolute_uri(reverse("aushang:anzeige", args=[aushang.schluessel]))


@never_cache
@einrichten
def liste(request):
    form = NeuForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        aushang = form.save()
        messages.success(request, f"Aushang „{aushang}“ angelegt. Jetzt Seiten hinzufügen.")
        return redirect("aushang:bearbeiten", aushang.pk)
    aushaenge = list(Aushang.objects.prefetch_related("seiten"))
    for a in aushaenge:
        a.link = _link(request, a)
    return render(request, "aushang/liste.html", {"aushaenge": aushaenge, "form": form})


@never_cache
@einrichten
def bearbeiten(request, pk):
    aushang = get_object_or_404(Aushang, pk=pk)
    wahl = inhalt.wahlmoeglichkeiten(request.user)
    form = AushangForm(instance=aushang)
    seite_form = SeiteForm(wahl=wahl)
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "einstellungen":
            form = AushangForm(request.POST, instance=aushang)
            if form.is_valid():
                form.save()
                return redirect("aushang:bearbeiten", pk)
        elif aktion == "seite":
            seite_form = SeiteForm(request.POST, wahl=wahl)
            if seite_form.is_valid():
                art, _, wert = seite_form.cleaned_data["seite"].partition(":")
                letzte = aushang.seiten.aggregate(m=Max("reihenfolge"))["m"] or 0
                AushangSeite.objects.create(aushang=aushang, art=art, wert=wert,
                                            monate=seite_form.cleaned_data["monate"],
                                            reihenfolge=letzte + 1)  # fmt: skip
                return redirect("aushang:bearbeiten", pk)
        elif aktion in ("hoch", "runter", "entfernen"):
            _seite_aendern(aushang, aktion, request.POST.get("seite"))
            return redirect("aushang:bearbeiten", pk)
        elif aktion == "schluessel":
            aushang.schluessel = neuer_schluessel()
            aushang.save(update_fields=["schluessel"])
            messages.success(request, "Neuer Link erzeugt. Der alte zeigt nichts mehr an.")
            return redirect("aushang:bearbeiten", pk)
    arten = module.aushangseiten()
    seiten = list(aushang.seiten.all())
    for s in seiten:
        s.bezeichnung = inhalt.bezeichnung(s, arten)
    return render(request, "aushang/bearbeiten.html", {
        "aushang": aushang, "form": form, "seite_form": seite_form, "seiten": seiten,
        "link": _link(request, aushang), "wahl": wahl,
    })  # fmt: skip


def _seite_aendern(aushang, aktion, seite_pk) -> None:
    seiten = list(aushang.seiten.all())
    i = next((i for i, s in enumerate(seiten) if str(s.pk) == str(seite_pk)), None)
    if i is None:
        raise Http404
    if aktion == "entfernen":
        seiten.pop(i).delete()
    elif aktion == "hoch" and i > 0:
        seiten[i - 1], seiten[i] = seiten[i], seiten[i - 1]
    elif aktion == "runter" and i < len(seiten) - 1:
        seiten[i + 1], seiten[i] = seiten[i], seiten[i + 1]
    for nr, s in enumerate(seiten, start=1):
        if s.reihenfolge != nr:
            s.reihenfolge = nr
            s.save(update_fields=["reihenfolge"])


@require_POST
@einrichten
def loeschen(request, pk):
    aushang = get_object_or_404(Aushang, pk=pk)
    papierkorb.loeschen(request.user, "Aushang-Monitor", str(aushang), aushang,
                        recht="aushang.einrichten")  # fmt: skip
    messages.success(request, f"„{aushang}“ in den Papierkorb gelegt.")
    return redirect("aushang:liste")


@never_cache
def anzeige(request, schluessel):
    """Der Monitor selbst: ohne Anmeldung, nur mit dem Schlüssel im Link. Fragt der Monitor
    selbst nach dem neuen Stand (aushang.js) und der Link gilt nicht mehr, antwortet er mit 204:
    Der Monitor leert dann den Bildschirm (ohne Fehlermeldung in der Browser-Konsole)."""
    aushang = Aushang.objects.filter(schluessel=schluessel, aktiv=True).first()
    if aushang is None:
        if request.headers.get("X-Aushang"):
            return HttpResponse(status=204)
        raise Http404
    jetzt = timezone.localtime()
    return render(request, "aushang/anzeige.html", {
        "aushang": aushang, "folien": inhalt.folien(aushang, jetzt.date()), "jetzt": jetzt,
    })  # fmt: skip
