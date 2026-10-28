"""Aushang-Monitore einrichten und anzeigen (ADR 0080); was angezeigt wird, in ``anzeige.py``."""

import segno
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from apps.aushang import anzeige as inhalt
from apps.aushang import pin
from apps.aushang.forms import AushangForm, NeuForm, PinForm, SeiteForm
from apps.aushang.models import Aushang, AushangSeite, MonitorPin, neuer_schluessel
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


def _aushang_oder_nichts(request, schluessel):
    """Der Aushang zum Schlüssel; fragt der Monitor selbst nach (aushang.js) und der Link gilt
    nicht mehr, antwortet er mit 204: Der Monitor leert dann den Bildschirm (ohne Fehlermeldung
    in der Browser-Konsole)."""
    aushang = Aushang.objects.filter(schluessel=schluessel, aktiv=True).first()
    if aushang is None:
        if request.headers.get("X-Aushang"):
            return None, HttpResponse(status=204)
        raise Http404
    return aushang, None


def _qr(adresse: str) -> str:
    return segno.make(adresse, error="m").svg_inline(scale=4, title="QR-Code: Plan am Handy öffnen")


@never_cache
def anzeige(request, schluessel):
    """Der Monitor selbst: ohne Anmeldung, nur mit dem Schlüssel im Link."""
    aushang, leer = _aushang_oder_nichts(request, schluessel)
    if leer:
        return leer
    jetzt = timezone.localtime()
    folien = [
        (titel, html, _qr(request.build_absolute_uri(adresse)) if aushang.qr_code else "")
        for titel, html, adresse in inhalt.folien(aushang, jetzt.date())
    ]
    return render(request, "aushang/anzeige.html", {
        "aushang": aushang, "folien": folien, "jetzt": jetzt,
        "platz_url": reverse("aushang:platz", args=[schluessel]),
    })  # fmt: skip


@never_cache
@require_http_methods(["GET", "POST"])
def platz(request, schluessel):
    """Dialog am Monitor zu einem Platz (GET) und die Änderung mit persönlicher PIN (POST)."""
    aushang, leer = _aushang_oder_nichts(request, schluessel)
    if leer:
        return leer
    if not aushang.aendern:
        raise Http404
    kennung = request.POST.get("platz") or request.GET.get("platz", "")
    if request.method == "POST":
        try:
            meldung = inhalt.aendern(aushang, kennung, request.POST,
                                     request.build_absolute_uri("/").rstrip("/"))  # fmt: skip
        except ValueError as fehler:
            return JsonResponse({"ok": False, "fehler": str(fehler)})
        return JsonResponse({"ok": True, "meldung": meldung})
    dialog = inhalt.platz_dialog(kennung)
    if dialog is None:
        raise Http404
    return render(request, "aushang/_platz.html", {"d": dialog, "mindestlaenge": pin.MINDESTLAENGE})


@never_cache
@login_required
def meine_pin(request):
    """Eigene PIN für das Ändern am Aushang-Monitor festlegen, ändern oder löschen."""
    form = PinForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("aktion") == "loeschen":
            pin.entfernen(request.user)
            messages.success(request, "Ihre PIN ist gelöscht.")
            return redirect("aushang:meine_pin")
        if form.is_valid():
            pin.setzen(request.user, form.cleaned_data["pin"])
            messages.success(request, "Ihre PIN ist gespeichert.")
            return redirect("aushang:meine_pin")
    eintrag = MonitorPin.objects.filter(benutzer=request.user).first()
    return render(request, "aushang/meine_pin.html", {"form": form, "eintrag": eintrag})
