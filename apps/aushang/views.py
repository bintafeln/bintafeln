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
from apps.aushang import pin, stempeln
from apps.aushang.forms import AushangForm, NeuForm, PinForm, SeiteForm, ZeitraumForm
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
                                            reihenfolge=letzte + 1,
                                            **seite_form.werte())  # fmt: skip
                return redirect("aushang:bearbeiten", pk)
        elif aktion == "zeitraum":
            s = get_object_or_404(AushangSeite, aushang=aushang, pk=request.POST.get("seite"))
            zeitraum = ZeitraumForm(request.POST)
            if zeitraum.is_valid():
                for feld, wert in zeitraum.werte().items():
                    setattr(s, feld, wert)
                s.save(update_fields=["monate", "wochen"])
                messages.success(request, f"Zeitraum: {s.zeitraum_text()}.")
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
        s.zeitraum_form = ZeitraumForm(initial=ZeitraumForm.fuer(s), auto_id=f"z{s.pk}_%s")
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
    # omitsize=True: SVG mit viewBox statt fester width/height, damit der per CSS verkleinerte
    # Code ganz mitskaliert und nicht rechts/unten abgeschnitten (und damit unscannbar) wird.
    return segno.make(adresse, error="m").svg_inline(
        scale=4, omitsize=True, title="QR-Code: Plan am Handy öffnen"
    )


@never_cache
def anzeige(request, schluessel):
    """Der Monitor selbst: ohne Anmeldung, nur mit dem Schlüssel im Link."""
    aushang, leer = _aushang_oder_nichts(request, schluessel)
    if leer:
        return leer
    jetzt = timezone.localtime()
    folien = [
        (
            titel,
            html,
            _qr(request.build_absolute_uri(adresse)) if aushang.qr_code and adresse else "",
            kurz,
        )
        for titel, html, adresse, kurz in inhalt.folien(aushang, jetzt.date())
    ]
    return render(request, "aushang/anzeige.html", {
        "aushang": aushang, "folien": folien, "jetzt": jetzt,
        "platz_url": reverse("aushang:platz", args=[schluessel]),
        "stempeln_url": reverse("aushang:stempeln", args=[schluessel])
        if stempeln.an(aushang) else "",
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


def _qr_stempeln(request, aushang) -> str:
    adresse = request.build_absolute_uri(
        reverse("aushang:stempeln_handy", args=[stempeln.marke(aushang)])
    )
    return segno.make(adresse, error="m").svg_inline(
        scale=4, omitsize=True, title="QR-Code: mit dem Handy stempeln"
    )


@never_cache
@require_http_methods(["GET", "POST"])
def stempeln_monitor(request, schluessel):
    """Fenster „Stempeln“ am Monitor (GET, mit ``?qr=1`` nur ein frischer QR-Code) und das
    Stempeln mit Name und persönlicher PIN (POST): erst prüfen, dann Kommen, Pause oder Gehen."""
    from apps.personal import arbeitszeit

    aushang, leer = _aushang_oder_nichts(request, schluessel)
    if leer:
        return leer
    if not stempeln.an(aushang):
        raise Http404
    if request.method == "GET":
        if request.GET.get("qr"):
            if not aushang.stempeln_qr:
                raise Http404
            return HttpResponse(_qr_stempeln(request, aushang), content_type="image/svg+xml")
        return render(request, "aushang/_stempeln.html", {
            "aushang": aushang, "mindestlaenge": pin.MINDESTLAENGE,
            "personen": stempeln.mit_pin() if aushang.stempeln_pin else [],
            "qr": _qr_stempeln(request, aushang) if aushang.stempeln_qr else "",
            "wechsel": stempeln.WECHSEL_SEKUNDEN,
        })  # fmt: skip
    if not aushang.stempeln_pin:
        raise Http404
    try:
        person = pin.pruefen(request.POST.get("person"), request.POST.get("pin"))
    except ValueError as fehler:
        return JsonResponse({"ok": False, "fehler": str(fehler)})
    if not arbeitszeit.erfasst(person):
        return JsonResponse({"ok": False, "fehler": "Für diese Person wird keine Arbeitszeit "
                             "erfasst."})  # fmt: skip
    aktion = request.POST.get("aktion", "")
    if aktion not in ("kommen", "pause", "gehen"):  # erst nur prüfen: was kann sie stempeln?
        text, moeglich = arbeitszeit.stand(person)
        return JsonResponse({"ok": True, "name": str(person), "stand": text,
                             "aktionen": moeglich})  # fmt: skip
    try:
        meldung = arbeitszeit.stempeln(person, aktion)
    except arbeitszeit.StempelFehler as fehler:
        return JsonResponse({"ok": False, "fehler": str(fehler)})
    return JsonResponse({"ok": True, "fertig": True, "meldung": f"{person}: {meldung}"})


@never_cache
def stempeln_handy(request, marke):
    """Ziel des QR-Codes am Monitor: Dieses Handy darf für ein paar Minuten stempeln. Die
    Freigabe hängt an der Sitzung und bleibt über die Anmeldung erhalten – wer noch nicht
    angemeldet ist, meldet sich danach an (der Code selbst gilt nur kurz)."""
    from django.contrib.auth.views import redirect_to_login

    from apps.personal import arbeitszeit

    ziel = reverse("personal:meine_arbeitszeit")
    gueltig = stempeln.einloesen(marke) is not None
    if gueltig:
        arbeitszeit.freigeben(request)
    if not request.user.is_authenticated:
        return redirect_to_login(ziel)
    if not arbeitszeit.darf_stempeln(request.user):
        messages.error(request, "Für Ihr Konto wird keine Arbeitszeit erfasst.")
        return redirect("core:start")
    if gueltig:
        messages.success(request, "Vor Ort bestätigt: Sie können jetzt stempeln.")
    else:
        messages.error(request, "Dieser QR-Code ist abgelaufen. Bitte den Code am Monitor noch "
                       "einmal scannen – er ändert sich laufend.")  # fmt: skip
    return redirect(ziel)


@never_cache
@login_required
def meine_pin(request):
    """Eigene PIN für das Ändern am Aushang-Monitor festlegen, ändern oder löschen."""
    if request.user.stelle_id:  # Konto einer Ausgabestelle gehört keiner Person (ADR 0059, 0080)
        raise Http404
    form = PinForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("aktion") == "loeschen":
            pin.entfernen(request.user)
            messages.success(request, "Ihre PIN ist gelöscht.")
            return redirect("konten:mein_konto")
        if form.is_valid():
            pin.setzen(request.user, form.cleaned_data["pin"])
            messages.success(request, "Ihre PIN ist gespeichert.")
            return redirect("konten:mein_konto")
    eintrag = MonitorPin.objects.filter(benutzer=request.user).first()
    return render(request, "aushang/meine_pin.html", {"form": form, "eintrag": eintrag})
