"""Ansichten des Moduls Touren (ADR 0147): Stationen ansehen, pflegen, importieren und ins
Adressbuch übertragen."""

import base64
import datetime as dt

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.adressen.forms import ImportForm
from apps.core import geheimnis, listen, papierkorb
from apps.konten import rollen
from apps.touren import adressbuch, importieren, lieferscheine
from apps.touren.forms import StationForm, neue_kennung
from apps.touren.models import Station, Tour

sehen = rollen.recht_erforderlich("touren.stationen")
bearbeiten_recht = rollen.recht_erforderlich("touren.stationen_bearbeiten")
SITZUNG_IMPORT = "touren_import"
STAND = [("aktiv", "aktive"), ("inaktiv", "nicht mehr angefahren"), ("alle", "alle")]


def _darf_uebertragen(benutzer) -> bool:
    return rollen.hat_recht(benutzer, "touren.stationen_bearbeiten") and rollen.hat_recht(
        benutzer, "adressen.bearbeiten")  # fmt: skip


def _gefiltert(request):
    f = {"art": request.GET.get("art", ""), "stand": request.GET.get("stand", "aktiv"),
         "q": request.GET.get("q", "").strip()}  # fmt: skip
    stationen = Station.objects.select_related("adresse")
    if f["stand"] == "aktiv":
        stationen = stationen.filter(aktiv=True)
    elif f["stand"] == "inaktiv":
        stationen = stationen.filter(aktiv=False)
    if f["art"] in Station.Art.values:
        stationen = stationen.filter(art=f["art"])
    if f["q"]:
        q = f["q"]
        stationen = stationen.filter(
            Q(name__icontains=q)
            | Q(kette__icontains=q)
            | Q(strasse__icontains=q)
            | Q(plz__startswith=q)
            | Q(ort__icontains=q)
            | Q(ortsteil__icontains=q)
            | Q(kennung__iexact=q)
            | Q(filialnummer__iexact=q)
        )
    return stationen, f


@never_cache
@sehen
def stationen(request):
    umleiten = listen.filter_merken(request, "touren_stationen", ["art", "stand", "q"])
    if umleiten is not None:
        return umleiten
    liste, f = _gefiltert(request)
    if request.GET.get("format") == "csv":
        # Die ganze Liste mit Kontaktdaten als Datei: nur für die, die sie pflegen
        if not rollen.hat_recht(request.user, "touren.stationen_bearbeiten"):
            raise PermissionDenied
        antwort = HttpResponse(
            importieren.exportieren(liste), content_type="text/csv; charset=utf-8"
        )
        antwort["Content-Disposition"] = (
            f'attachment; filename="stationen-{timezone.localdate():%Y-%m-%d}.csv"'
        )
        return antwort
    return render(request, "touren/stationen.html", {
        "stationen": liste, "filter": f, "arten": Station.Art.choices, "staende": STAND,
        "darf_bearbeiten": rollen.hat_recht(request.user, "touren.stationen_bearbeiten"),
        "darf_uebertragen": _darf_uebertragen(request.user),
        "ohne_adressbuch": Station.objects.filter(aktiv=True, adresse__isnull=True).count(),
    })  # fmt: skip


@never_cache
@sehen
def station(request, pk):
    s = get_object_or_404(Station.objects.select_related("adresse"), pk=pk)
    return render(request, "touren/station.html", {
        "s": s, "zur_tour": _zur_tour(request),
        "darf_bearbeiten": rollen.hat_recht(request.user, "touren.stationen_bearbeiten"),
        "darf_uebertragen": _darf_uebertragen(request.user),
        "vorhanden": None if s.adresse_id else adressbuch.vorhandene(s),
        "lieferscheine_an": lieferscheine.an(),
    })  # fmt: skip


def _zur_tour(request) -> dict | None:
    """Kommt jemand aus einer Tour („Alle Angaben“), führt „zurück“ wieder dorthin – an die
    Stelle der Station – und nicht in die Stationsliste."""
    werte = request.GET
    if not werte.get("tour", "").isdigit() or not rollen.hat_recht(request.user, "touren.fahren"):
        return None
    tour = Tour.objects.filter(pk=int(werte["tour"])).first()
    if tour is None:
        return None
    url, anhang = reverse("touren:fahren", args=[tour.pk]), f"?tour={tour.pk}"
    try:
        tag = f"{dt.date.fromisoformat(werte.get('tag', '')):%Y-%m-%d}"
        url, anhang = f"{url}?tag={tag}", f"{anhang}&tag={tag}"
    except ValueError:
        pass
    if werte.get("halt", "").isdigit():
        url += f"#halt-{int(werte['halt'])}"
    return {"url": url, "name": tour.name, "anhang": anhang}


@never_cache
@bearbeiten_recht
def bearbeiten(request, pk=None):
    s = get_object_or_404(Station, pk=pk) if pk else None
    form = StationForm(request.POST or None, instance=s,
                       initial=None if s else {"kennung": neue_kennung()})  # fmt: skip
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        s.geaendert_am, s.geaendert_von = timezone.now(), request.user.get_username()
        s.save()
        if pk is None:
            messages.success(request, f"Station „{s}“ angelegt.")
        return redirect("touren:station", pk=s.pk)
    return render(request, "touren/bearbeiten.html", {"form": form, "s": s})


@require_POST
@bearbeiten_recht
def loeschen(request, pk):
    s = get_object_or_404(Station, pk=pk)
    papierkorb.loeschen(request.user, "Station", str(s), s, recht="touren.stationen_bearbeiten")
    messages.success(request, f"Station „{s}“ in den Papierkorb gelegt.")
    return redirect("touren:stationen")


@require_POST
@bearbeiten_recht
def uebertragen(request, pk):
    if not _darf_uebertragen(request.user):
        raise PermissionDenied
    s = get_object_or_404(Station, pk=pk)
    adresse, neu = adressbuch.uebertragen(s, request.user.get_username())
    messages.success(request, f"Im Adressbuch angelegt: {adresse}." if neu
                     else f"Mit dem Eintrag im Adressbuch verknüpft: {adresse}.")  # fmt: skip
    return redirect("touren:station", pk=s.pk)


@require_POST
@bearbeiten_recht
def alle_uebertragen(request):
    """Alle aktiven Stationen ohne Eintrag im Adressbuch übertragen."""
    if not _darf_uebertragen(request.user):
        raise PermissionDenied
    neu = verknuepft = 0
    for s in Station.objects.filter(aktiv=True, adresse__isnull=True).order_by("pk"):
        _, angelegt = adressbuch.uebertragen(s, request.user.get_username())
        neu += angelegt
        verknuepft += not angelegt
    messages.success(request, f"Ins Adressbuch übertragen: {neu} neu angelegt, "
                     f"{verknuepft} mit vorhandenen Einträgen verknüpft.")  # fmt: skip
    return redirect("touren:stationen")


def _bericht_aus_sitzung(request):
    gespeichert = request.session.get(SITZUNG_IMPORT)
    if not gespeichert:
        return None
    roh = geheimnis.bytes_entschluesseln(base64.b64decode(gespeichert))
    return importieren.pruefen(importieren.text_lesen(roh)) if roh else None


@never_cache
@bearbeiten_recht
def importieren_ansicht(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    bericht = None
    if request.method == "POST" and request.POST.get("schritt") == "uebernehmen":
        try:
            bericht = _bericht_aus_sitzung(request)
        except importieren.ImportFehler:
            bericht = None
        request.session.pop(SITZUNG_IMPORT, None)
        if bericht is None:
            messages.error(request, "Keine geprüfte Datei vorhanden. Bitte erneut hochladen.")
            return redirect("touren:importieren")
        neu, geaendert = importieren.uebernehmen(bericht, request.user.get_username())
        messages.success(request, f"Stationen übernommen: {neu} neu, {geaendert} aktualisiert.")
        return redirect("touren:stationen")
    if request.method == "POST" and form.is_valid():
        roh = form.cleaned_data["datei"].read()
        try:
            bericht = importieren.pruefen(importieren.text_lesen(roh))
        except importieren.ImportFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("touren:importieren")
        # Bis zum Übernehmen verschlüsselt in der Sitzung (Ansprechpartner sind Personendaten)
        request.session[SITZUNG_IMPORT] = base64.b64encode(
            geheimnis.bytes_verschluesseln(roh)).decode()  # fmt: skip
    return render(request, "touren/importieren.html", {
        "form": form, "bericht": bericht, "spalten": importieren.SPALTEN,
        "pflicht": importieren.PFLICHT, "arten": Station.Art.values,
    })  # fmt: skip
