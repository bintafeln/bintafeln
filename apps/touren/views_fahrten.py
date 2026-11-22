"""Fahrten (ADR 0151): am Handy beginnen und beenden, im Büro das Fahrtenbuch."""

import csv
import datetime as dt
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import listenexport, papierkorb, privatdateien
from apps.konten import rollen
from apps.touren import fahrten, meldungen
from apps.touren.forms import FahrzeugDokumentForm, FahrzeugForm
from apps.touren.models import Fahrt, Fahrzeug, FahrzeugDokument, Fahrzeugmeldung, Tour

fahren_recht = rollen.recht_erforderlich("touren.fahren")
buch = rollen.recht_erforderlich("touren.fahrten")


@require_POST
@fahren_recht
def beginnen(request, pk):
    tour = get_object_or_404(Tour.objects.select_related("fahrdienst_tour"), pk=pk)
    try:
        fahrten.beginnen(tour, request.user, request.POST.get("km_start"),
                         request.POST.get("fahrzeug"))  # fmt: skip
    except fahrten.FahrtFehler as grund:
        messages.error(request, str(grund))
    else:
        messages.success(request, "Fahrt begonnen. Gute Fahrt!")
    return redirect(reverse("touren:fahren", args=[tour.pk]))


@require_POST
@fahren_recht
def beenden(request, pk):
    fahrt = get_object_or_404(Fahrt.objects.select_related("tour__fahrdienst_tour"), pk=pk)
    try:
        fahrten.beenden(fahrt, request.user, request.POST.get("km_ende"))
    except fahrten.FahrtFehler as grund:
        messages.error(request, str(grund))
        ziel = reverse("touren:fahren", args=[fahrt.tour_id]) if fahrt.tour_id else None
        return redirect(f"{ziel}#fahrt" if ziel else "touren:heute")
    messages.success(request, f"Tour beendet: {fahrt.km} km gefahren. Danke!")
    if request.POST.get("meldung", "").strip():  # gleich mitgemeldet: Beanstandung, getankt …
        _melden(request, fahrt)
    return redirect("touren:heute")


def _melden(request, fahrt) -> bool:
    try:
        meldungen.melden(fahrt, request.user, request.POST.get("meldung_art", ""),
                         request.POST.get("meldung", ""))  # fmt: skip
    except meldungen.MeldungFehler as grund:
        messages.error(request, str(grund))
        return False
    messages.success(request, "Meldung zum Fahrzeug ist bei der Fahrdienstleitung.")
    return True


@require_POST
@fahren_recht
def melden(request, pk):
    """Etwas zum Fahrzeug melden, ohne die Tour zu beenden (oder danach)."""
    fahrt = get_object_or_404(Fahrt.objects.select_related("tour__fahrdienst_tour"), pk=pk)
    _melden(request, fahrt)
    if fahrt.tour_id:
        return redirect(reverse("touren:fahren", args=[fahrt.tour_id]) + "#fahrt")
    return redirect("touren:heute")


@never_cache
@buch
def meldungen_liste(request):
    """Alle Meldungen zum Fahrzeug; offene zuerst."""
    f = {"stand": request.GET.get("stand", "offen"), "fahrzeug": request.GET.get("fahrzeug", "")}
    liste = Fahrzeugmeldung.objects.select_related("fahrzeug")
    if f["stand"] == "offen":
        liste = liste.filter(erledigt_am__isnull=True)
    if f["fahrzeug"].isdigit():
        liste = liste.filter(fahrzeug_id=int(f["fahrzeug"]))
    else:
        f["fahrzeug"] = ""
    seite = Paginator(liste, 50).get_page(request.GET.get("seite"))
    return render(request, "touren/meldungen.html", {
        "seite": seite, "zeilen": seite.object_list, "filter": f,
        "fahrzeuge": Fahrzeug.objects.all(), "offen": meldungen.offene().count(),
    })  # fmt: skip


@require_POST
@buch
def meldung_erledigen(request, pk):
    meldung = get_object_or_404(Fahrzeugmeldung, pk=pk)
    if "oeffnen" in request.POST:
        meldungen.wieder_oeffnen(meldung)
    else:
        meldungen.erledigen(meldung, request.user, request.POST.get("notiz", ""))
    ziel = request.POST.get("zurueck", "")
    return redirect(ziel if ziel.startswith("/") and not ziel.startswith("//")
                    else "touren:meldungen")  # fmt: skip


def _gefiltert(request):
    f = {"q": request.GET.get("q", "").strip(), "von": request.GET.get("von", ""),
         "bis": request.GET.get("bis", ""), "fahrzeug": request.GET.get("fahrzeug", ""),
         "stand": request.GET.get("stand", "")}  # fmt: skip
    liste = Fahrt.objects.select_related("fahrzeug", "tour")
    if f["q"]:
        liste = liste.filter(Q(tour_name__icontains=f["q"]) | Q(besetzung__icontains=f["q"])
                             | Q(fahrzeug_name__icontains=f["q"]))  # fmt: skip
    for feld, suche in (("von", "datum__gte"), ("bis", "datum__lte")):
        try:
            liste = liste.filter(**{suche: dt.date.fromisoformat(f[feld])})
        except ValueError:
            f[feld] = ""
    if f["fahrzeug"].isdigit():
        liste = liste.filter(fahrzeug_id=int(f["fahrzeug"]))
    else:
        f["fahrzeug"] = ""
    if f["stand"] == "offen":
        liste = liste.filter(km_ende__isnull=True)
    return f, liste


@never_cache
@buch
def liste(request):
    """Das Fahrtenbuch: alle Fahrten, neueste zuerst, mit Summe der Kilometer."""
    f, fahrten_ = _gefiltert(request)
    if request.GET.get("export") == "csv":
        zeilen = []
        for x in fahrten_:
            zeilen.append([x.datum.strftime("%d.%m.%Y"), x.tour_name, x.fahrzeug_name, x.besetzung,
                           x.km_start, "" if x.km_ende is None else x.km_ende,
                           "" if x.km is None else x.km,
                           timezone.localtime(x.begonnen_am).strftime("%H:%M"),
                           timezone.localtime(x.beendet_am).strftime("%H:%M")
                           if x.beendet_am else ""])  # fmt: skip
            if x.km_unbekannt:  # davor gefahren, ohne Eintrag
                zeilen.append([f"vor {x.datum:%d.%m.%Y}", "unbekannt", x.fahrzeug_name, "unbekannt",
                               x.km_vorher, x.km_start, x.km_unbekannt, "", ""])  # fmt: skip
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";")
        schreiber.writerow(["Datum", "Tour", "Fahrzeug", "Besetzung", "km Abfahrt", "km Ankunft",
                            "km gefahren", "Beginn", "Ende"])  # fmt: skip
        schreiber.writerows(zeilen)
        return listenexport.ausliefern(request, "Fahrtenbuch", "fahrten", puffer.getvalue(),
                                       weiter=reverse("touren:fahrten"))  # fmt: skip
    summe = sum(x.km or 0 for x in fahrten_)
    unbekannt = sum(x.km_unbekannt or 0 for x in fahrten_)
    seite = Paginator(fahrten_, 50).get_page(request.GET.get("seite"))
    return render(request, "touren/fahrten.html", {
        "seite": seite, "zeilen": seite.object_list, "filter": f, "summe": summe,
        "unbekannt": unbekannt,
        "fahrzeuge": Fahrzeug.objects.all(), "heute": timezone.localdate(),
        "offen": Fahrt.objects.filter(km_ende__isnull=True,
                                      datum__lt=timezone.localdate()).count(),
    })  # fmt: skip


@never_cache
@buch
def bearbeiten(request, pk):
    fahrt = get_object_or_404(Fahrt.objects.select_related("fahrzeug"), pk=pk)
    if request.method == "POST":
        try:
            p = request.POST
            fahrten.berichtigen(fahrt, request.user, p.get("km_start"), p.get("km_ende"),
                                p.get("fahrzeug"))  # fmt: skip
        except fahrten.FahrtFehler as grund:
            messages.error(request, str(grund))
        else:
            messages.success(request, "Fahrt berichtigt.")
            return redirect("touren:fahrten")
    return render(request, "touren/fahrt.html", {
        "fahrt": fahrt,
        "fahrzeuge": Fahrzeug.objects.filter(Q(aktiv=True) | Q(pk=fahrt.fahrzeug_id)),
    })  # fmt: skip


@require_POST
@buch
def fahrt_loeschen(request, pk):
    fahrt = get_object_or_404(Fahrt.objects.select_related("fahrzeug"), pk=pk)
    fahrten.loeschen(fahrt, request.user)
    messages.success(request, f"Fahrt „{fahrt.tour_name}“ am {fahrt.datum:%d.%m.%Y} gelöscht. "
                     "Sie liegt im Papierkorb.")  # fmt: skip
    return redirect("touren:fahrten")


# ── Papiere zum Fahrzeug (ADR 0160) ─────────────────────────────────────────


def _papiere_sehen(benutzer) -> None:
    """Fahrzeugschein und -brief sieht die Fahrdienstleitung: wer Touren plant oder das
    Fahrtenbuch führt."""
    if not (rollen.hat_recht(benutzer, "touren.planen")
            or rollen.hat_recht(benutzer, "touren.fahrten")):  # fmt: skip
        raise PermissionDenied


def _fahrzeugarten() -> list[str]:
    """Schon benutzte Fahrzeugarten als Vorschläge."""
    return sorted(set(Fahrzeug.objects.exclude(typ="").values_list("typ", flat=True)))


@never_cache
@rollen.recht_erforderlich("touren.planen")
def fahrzeug_neu(request):
    naechste = (Fahrzeug.objects.aggregate(n=Max("reihenfolge"))["n"] or 0) + 1
    form = FahrzeugForm(request.POST or None, initial={"reihenfolge": naechste, "aktiv": True})
    if request.method == "POST" and form.is_valid():
        wagen = form.save()
        messages.success(request, f"Fahrzeug „{wagen.name}“ angelegt. Jetzt können Sie Papiere "
                         "hinterlegen.")  # fmt: skip
        return redirect(f"{reverse('touren:fahrzeug', args=[wagen.pk])}#papiere")
    return render(request, "touren/fahrzeug.html", {
        "form": form, "darf_aendern": True, "fahrzeugarten": _fahrzeugarten(),
    })  # fmt: skip


@never_cache
@login_required
def fahrzeug(request, pk):
    """Ein Fahrzeug: Angaben ändern und Papiere hinterlegen (wer Touren plant); ansehen darf
    auch, wer das Fahrtenbuch führt."""
    _papiere_sehen(request.user)
    wagen = get_object_or_404(Fahrzeug, pk=pk)
    darf_aendern = rollen.hat_recht(request.user, "touren.planen")
    if request.method == "POST" and not darf_aendern:
        raise PermissionDenied
    angaben = "angaben" in request.POST
    form = FahrzeugForm(request.POST if angaben else None, instance=wagen)
    papier_form = FahrzeugDokumentForm(
        None if angaben else request.POST or None, None if angaben else request.FILES or None
    )
    if request.method == "POST" and angaben and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("touren:fahrzeug", pk=wagen.pk)
    if request.method == "POST" and not angaben and papier_form.is_valid():
        try:
            datei = papier_form.cleaned_data["datei"]
            name = privatdateien.speichern(FahrzeugDokument.ORDNER, datei, max_mb=10)
        except privatdateien.DateiFehler as grund:
            papier_form.add_error("datei", str(grund))
        else:
            papier = papier_form.save(commit=False)
            papier.fahrzeug, papier.datei = wagen, name
            papier.datei_typ = papier_form.cleaned_data["datei"].content_type
            papier.hochgeladen_von_name = (
                request.user.get_full_name() or request.user.get_username()
            )[:150]
            papier.save()
            messages.success(request, f"{papier.titel} hinterlegt.")
            return redirect(f"{reverse('touren:fahrzeug', args=[wagen.pk])}#papiere")
    return render(request, "touren/fahrzeug.html", {
        "fahrzeug": wagen, "papiere": wagen.dokumente.all(), "form": form,
        "papier_form": papier_form, "darf_aendern": darf_aendern,
        "fahrzeugarten": _fahrzeugarten(),
    })  # fmt: skip


@never_cache
@login_required
def papier(request, pk):
    _papiere_sehen(request.user)
    dokument = get_object_or_404(FahrzeugDokument.objects.select_related("fahrzeug"), pk=pk)
    inhalt = privatdateien.lesen(FahrzeugDokument.ORDNER, dokument.datei)
    if inhalt is None:
        raise Http404("Keine lesbare Datei.")
    endung = {"application/pdf": "pdf", "image/png": "png", "image/webp": "webp"}.get(
        dokument.datei_typ, "jpg"
    )
    name = "".join(z if z.isalnum() else "-" for z in f"{dokument.titel}-{dokument.fahrzeug.name}")
    antwort = HttpResponse(inhalt, content_type=dokument.datei_typ or "application/octet-stream")
    antwort["Content-Disposition"] = f'inline; filename="{name}.{endung}"'
    antwort["X-Content-Type-Options"] = "nosniff"
    return antwort


@require_POST
@rollen.recht_erforderlich("touren.planen")
def papier_weg(request, pk):
    dokument = get_object_or_404(FahrzeugDokument.objects.select_related("fahrzeug"), pk=pk)
    wagen = dokument.fahrzeug
    papierkorb.loeschen(request.user, "Papier zum Fahrzeug", f"{dokument.titel} ({wagen})",
                        dokument, recht="touren.planen")  # fmt: skip
    messages.success(request, f"{dokument.titel} entfernt.")
    return redirect("touren:fahrzeug", pk=wagen.pk)
