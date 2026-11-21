"""Abholtouren (ADR 0148): die Ansicht für unterwegs (Handy) und das Planen der Touren."""

import base64
import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.adressen.forms import ImportForm
from apps.ausgabe.ampel import WOCHENTAGE
from apps.core import geheimnis, module, papierkorb
from apps.konten import rollen
from apps.touren import ablauf, importieren_touren, lieferscheine
from apps.touren.forms import HaltForm, KurzfristigForm, TourForm
from apps.touren.models import Halt, Tour

fahren_recht = rollen.recht_erforderlich("touren.fahren")
planen = rollen.recht_erforderlich("touren.planen")
SITZUNG_IMPORT = "touren_tourstationen_import"


def _tag(request) -> dt.date:
    try:
        return dt.date.fromisoformat(request.GET.get("tag", ""))
    except ValueError:
        return timezone.localdate()


# --- Unterwegs ----------------------------------------------------------------------------------


@never_cache
@fahren_recht
def heute(request):
    """Die Touren eines Tages; die eigenen stehen oben."""
    tag, heute_ = _tag(request), timezone.localdate()
    person = ablauf.person_von(request.user)
    zeilen = []
    for t in ablauf.touren_am(tag):
        wer = ablauf.besetzung(t, tag)
        zeilen.append({
            "tour": t, "besetzung": wer, "stationen": len(ablauf.halte(t, tag)),
            "meine": person is not None and any(
                b["person"] is not None and b["person"].pk == person.pk for b in wer),
        })  # fmt: skip
    zeilen.sort(key=lambda z: not z["meine"])
    return render(request, "touren/heute.html", {
        "tag": tag, "ist_heute": tag == heute_, "zeilen": zeilen,
        "davor": tag - dt.timedelta(days=1), "danach": tag + dt.timedelta(days=1),
        "darf_planen": rollen.hat_recht(request.user, "touren.planen"),
    })  # fmt: skip


@never_cache
@fahren_recht
def fahren(request, pk):
    """Eine Tour für unterwegs: Stationen der Reihe nach, je Station Navigation und Anfahrt."""
    tour = get_object_or_404(Tour.objects.select_related("fahrdienst_tour"), pk=pk)
    tag = tour.datum or _tag(request)
    halte = ablauf.halte(tour, tag)
    darf_schein = lieferscheine.an() and rollen.hat_recht(request.user, "touren.lieferschein")
    scheine = lieferscheine.am_tag(tag, [h.station_id for h in halte]) if darf_schein else {}
    for h in halte:
        h.schein = scheine.get(h.station_id)
        h.schein_moeglich = darf_schein and h.station.lieferschein
    return render(request, "touren/fahren.html", {
        "tour": tour, "tag": tag, "halte": halte, "faehrt": ablauf.faehrt_am(tour, tag),
        "besetzung": ablauf.besetzung(tour, tag),
        "routen": ablauf.routen([h.station for h in halte]),
        "darf_planen": rollen.hat_recht(request.user, "touren.planen"),
    })  # fmt: skip


# --- Planen -------------------------------------------------------------------------------------


@never_cache
@planen
def touren(request):
    heute_ = timezone.localdate()
    alle = list(Tour.objects.select_related("fahrdienst_tour").prefetch_related("halte"))
    return render(request, "touren/touren.html", {
        "regelmaessig": [t for t in alle if not t.datum],
        "kurzfristig": [t for t in alle if t.datum and t.datum >= heute_],
        "vergangen": [t for t in reversed(alle) if t.datum and t.datum < heute_][:20],
        "heute": heute_,
    })  # fmt: skip


def _form(request, tour, kurz):
    if kurz:
        start = None if tour else {"datum": _tag(request), "aktiv": True}
        return KurzfristigForm(request.POST or None, instance=tour, initial=start)
    return TourForm(request.POST or None, instance=tour, fahrdienst=module.aktiv("fahrdienst"))


@never_cache
@planen
def tour_neu(request):
    kurz = "kurz" in request.GET
    form = _form(request, None, kurz)
    if request.method == "POST" and form.is_valid():
        tour = form.save(commit=False)
        tour.angelegt_von = request.user.get_username()
        tour.save()
        form.save_m2m()
        messages.success(request, f"Tour „{tour}“ angelegt. Jetzt die Stationen anhängen.")
        return redirect("touren:tour", pk=tour.pk)
    return render(request, "touren/tour.html", {"form": form, "tour": None, "kurz": kurz})


@never_cache
@planen
def tour(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    form = _form(request, t, t.kurzfristig)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("touren:tour", pk=t.pk)
    tag = t.datum or timezone.localdate()
    return render(request, "touren/tour.html", {
        "form": form, "tour": t, "kurz": t.kurzfristig, "halte": ablauf.halte(t),
        "halt_form": HaltForm(tour=t), "wochentage": WOCHENTAGE,
        "besetzung": ablauf.besetzung(t, tag), "tag": tag,
        "aus_fahrerplan": bool(t.fahrdienst_tour_id) and not t.datum
        and module.aktiv("fahrdienst"),
    })  # fmt: skip


@require_POST
@planen
def tour_loeschen(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    papierkorb.loeschen(request.user, "Tour", str(t), t, recht="touren.planen")
    messages.success(request, f"Tour „{t}“ in den Papierkorb gelegt.")
    return redirect("touren:touren")


@require_POST
@planen
def tour_senden(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    ziel = reverse("touren:fahren", args=[t.pk])
    mit, ohne = ablauf.senden(t, request.build_absolute_uri(ziel))
    if mit:
        messages.success(request, f"Tour geschickt an: {', '.join(mit)}.")
    if ohne:
        messages.warning(request, f"Ohne E-Mail-Adresse, bitte anders Bescheid geben: "
                         f"{', '.join(ohne)}.")  # fmt: skip
    if not mit and not ohne:
        messages.error(request, "Niemand gewählt. Erst bei „Wer fährt“ Personen eintragen.")
    return redirect("touren:tour", pk=t.pk)


@require_POST
@planen
def halt_neu(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    form = HaltForm(request.POST, tour=t)
    if form.is_valid():
        ablauf.halt_anhaengen(t, form.cleaned_data["station"])
    else:
        messages.error(request, "Bitte eine Station wählen.")
    return redirect(reverse("touren:tour", args=[t.pk]) + "#stationen")


@require_POST
@planen
def halt_aendern(request, pk):
    """Ein Halt: früher, später, entfernen oder die Wochentage setzen."""
    h = get_object_or_404(Halt.objects.select_related("tour"), pk=pk)
    aktion = request.POST.get("aktion")
    if aktion in ("hoch", "runter"):
        ablauf.halt_bewegen(h, -1 if aktion == "hoch" else 1)
    elif aktion == "entfernen":
        h.delete()  # nur die Zuordnung; die Station bleibt
    elif aktion == "tage":
        gewaehlt = request.POST.getlist("wochentage")
        h.wochentage = ", ".join(t for t in WOCHENTAGE if t in gewaehlt)
        h.save(update_fields=["wochentage"])
    return redirect(reverse("touren:tour", args=[h.tour_id]) + "#stationen")


# --- Import der Stationsfolgen ------------------------------------------------------------------


def _bericht_aus_sitzung(request):
    gespeichert = request.session.get(SITZUNG_IMPORT)
    if not gespeichert:
        return None
    roh = geheimnis.bytes_entschluesseln(base64.b64decode(gespeichert))
    return importieren_touren.pruefen(importieren_touren.text_lesen(roh)) if roh else None


@never_cache
@planen
def touren_importieren(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    bericht = None
    if request.method == "POST" and request.POST.get("schritt") == "uebernehmen":
        try:
            bericht = _bericht_aus_sitzung(request)
        except importieren_touren.ImportFehler:
            bericht = None
        request.session.pop(SITZUNG_IMPORT, None)
        if bericht is None:
            messages.error(request, "Keine geprüfte Datei vorhanden. Bitte erneut hochladen.")
            return redirect("touren:touren_importieren")
        anzahl, halte = importieren_touren.uebernehmen(bericht, request.user.get_username())
        messages.success(request, f"{anzahl} Tour{'en' if anzahl != 1 else ''} mit {halte} "
                         "Stationen übernommen.")  # fmt: skip
        return redirect("touren:touren")
    if request.method == "POST" and form.is_valid():
        roh = form.cleaned_data["datei"].read()
        try:
            bericht = importieren_touren.pruefen(importieren_touren.text_lesen(roh))
        except importieren_touren.ImportFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("touren:touren_importieren")
        request.session[SITZUNG_IMPORT] = base64.b64encode(
            geheimnis.bytes_verschluesseln(roh)).decode()  # fmt: skip
    return render(request, "touren/touren_importieren.html", {
        "form": form, "bericht": bericht, "spalten": importieren_touren.SPALTEN,
    })  # fmt: skip
