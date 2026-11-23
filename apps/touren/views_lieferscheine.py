"""Lieferscheine (ADR 0149): unterwegs ausfüllen und unterschreiben, im Büro ansehen und
nachsenden, Einstellungen und Warengruppen."""

import datetime as dt

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import papierkorb
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.touren import lieferscheine
from apps.touren.forms import (
    EinrichtenForm,
    EinstellungenForm,
    KurztexteFormSet,
    UmstaendeFormSet,
    WarengruppenFormSet,
)
from apps.touren.models import (
    Fahrzeug,
    Lieferschein,
    Position,
    Station,
    Tour,
    TourenEinstellungen,
)

ausfuellen_recht = rollen.recht_erforderlich("touren.lieferschein")
sehen = rollen.recht_erforderlich("touren.lieferscheine")
einstellen = rollen.recht_erforderlich("einstellungen.touren")


def _tag(wert) -> dt.date:
    try:
        return dt.date.fromisoformat(wert or "")
    except ValueError:
        return timezone.localdate()


def _zurueck(tour, tag, station):
    if tour:
        return f"{reverse('touren:fahren', args=[tour.pk])}?tag={tag:%Y-%m-%d}"
    return reverse("touren:station", args=[station.pk])


@never_cache
@ausfuellen_recht
def ausfuellen(request, pk):
    """Lieferschein an einer Station: Mengen je Warengruppe, Unterschrift, senden."""
    station = get_object_or_404(Station, pk=pk)
    if not lieferscheine.moeglich(station):
        raise Http404("An dieser Station gibt es keinen Lieferschein.")
    quelle = request.POST if request.method == "POST" else request.GET
    tag = _tag(quelle.get("tag"))
    tour = Tour.objects.filter(pk=quelle.get("tour")).first() if (
        quelle.get("tour") or "").isdigit() else None  # fmt: skip
    fehler = ""
    if request.method == "POST":
        try:
            positionen = lieferscheine.positionen_lesen(request.POST)
            unterschrift = lieferscheine.unterschrift_lesen(request.POST.get("unterschrift"))
        except lieferscheine.LieferscheinFehler as grund:
            fehler = str(grund)
        else:
            ls = lieferscheine.erstellen(station, request.user, positionen, unterschrift,
                                         request.POST.get("anmerkung", ""), tour, tag,
                                         request.POST.get("art"))  # fmt: skip
            if lieferscheine.senden(ls):
                messages.success(request, f"Lieferschein Nr. {ls.nummer} gespeichert und an "
                                 f"{ls.gesendet_an} geschickt.")  # fmt: skip
            else:
                messages.warning(request, f"Lieferschein Nr. {ls.nummer} ist gespeichert, aber "
                                 f"nicht verschickt: {ls.mail_fehler} Das Büro kann ihn "
                                 "nachsenden.")  # fmt: skip
            return redirect(_zurueck(tour, tag, station))
    gruppen = lieferscheine.warengruppen()
    for g in gruppen:
        g.menge = request.POST.get(f"menge_{g.pk}", "")
        g.einheit = request.POST.get(f"einheit_{g.pk}", Position.Einheit.KISTEN)
    return render(request, "touren/lieferschein.html", {
        "station": station, "tour": tour, "tag": tag, "gruppen": gruppen, "fehler": fehler,
        "einheiten": Position.Einheit.choices, "anmerkung": request.POST.get("anmerkung", ""),
        "zurueck": _zurueck(tour, tag, station),
        "arten": Lieferschein.Art.choices,
        "art": lieferscheine.art_lesen(quelle.get("art")),
        "schon": Lieferschein.objects.filter(station=station, datum=tag).first(),
        "versand": TourenEinstellungen.laden().versand,
    })  # fmt: skip


@never_cache
@rollen.recht_erforderlich("touren.lieferscheine", "touren.lieferschein")
def pdf(request, pk):
    """Das PDF: für alle mit „Lieferscheine ansehen“; sonst nur für die, die es ausgefüllt
    haben oder an dem Tag auf dieser Tour gefahren sind – nie für andere Touren (ADR 0156)."""
    alle = rollen.hat_recht(request.user, "touren.lieferscheine")
    ls = Lieferschein.objects.select_related("tour__fahrdienst_tour").filter(pk=pk).first()
    if ls is None or not (alle or lieferscheine.darf_sehen(request.user, ls)):
        if alle:
            raise Http404
        raise PermissionDenied
    inhalt = lieferscheine.pdf(ls)
    if inhalt is None:
        raise Http404("Das PDF fehlt.")
    return pdf_antwort(inhalt, lieferscheine.dateiname(ls))


@never_cache
@sehen
def liste(request):
    f = {"q": request.GET.get("q", "").strip(), "von": request.GET.get("von", ""),
         "bis": request.GET.get("bis", ""), "stand": request.GET.get("stand", "")}  # fmt: skip
    scheine = Lieferschein.objects.select_related("station").prefetch_related("positionen")
    if f["q"]:
        q = f["q"]
        scheine = scheine.filter(Q(station_name__icontains=q) | Q(tour_name__icontains=q)
                                 | Q(unterschrieben_von__icontains=q)
                                 | Q(nummer=int(q) if q.isdigit() else -1))  # fmt: skip
    for feld, suche in (("von", "datum__gte"), ("bis", "datum__lte")):
        try:
            scheine = scheine.filter(**{suche: dt.date.fromisoformat(f[feld])})
        except ValueError:
            f[feld] = ""
    if f["stand"] == "offen":
        scheine = scheine.filter(gesendet_am__isnull=True)
    seite = Paginator(scheine, 50).get_page(request.GET.get("seite"))
    return render(request, "touren/lieferscheine.html", {
        "seite": seite, "zeilen": seite.object_list, "filter": f,
        "offen": Lieferschein.objects.filter(gesendet_am__isnull=True).count(),
    })  # fmt: skip


@require_POST
@sehen
def nachsenden(request, pk):
    ls = get_object_or_404(Lieferschein.objects.select_related("station"), pk=pk)
    if lieferscheine.senden(ls):
        messages.success(request, f"Lieferschein Nr. {ls.nummer} an {ls.gesendet_an} geschickt.")
    else:
        messages.error(request, f"Nicht verschickt: {ls.mail_fehler}")
    return redirect(request.POST.get("zurueck") or "touren:lieferscheine")


@require_POST
@sehen
def loeschen(request, pk):
    ls = get_object_or_404(Lieferschein, pk=pk)
    papierkorb.loeschen(request.user, "Lieferschein", f"Nr. {ls.nummer} ({ls.station_name})", ls,
                        recht="touren.lieferscheine")  # fmt: skip
    messages.success(request, f"Lieferschein Nr. {ls.nummer} in den Papierkorb gelegt.")
    return redirect("touren:lieferscheine")


@never_cache
@einstellen
def einstellungen(request):
    """Was nur der Admin entscheidet: Lieferscheine an/aus, Mailversand, Google-Schlüssel,
    ECO-Plattform, Aufbewahrung. Alles Übrige steht unter „Touren → Einrichten“."""
    form = EinstellungenForm(request.POST or None, instance=TourenEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("touren:einstellungen")
    return render(request, "touren/einstellungen.html", {"form": form})


@never_cache
@rollen.recht_erforderlich("touren.planen")
def einrichten(request):
    """Für die Fahrdienstleitung: Zentrale, Text der Lieferschein-Mail, Warengruppen und
    Fahrzeuge – ohne Umweg über die Einstellungen."""
    teile = {
        "einrichten": lambda daten: EinrichtenForm(daten, instance=TourenEinstellungen.laden()),
        "warengruppen": lambda daten: WarengruppenFormSet(daten, prefix="wg"),
        "umstaende": lambda daten: UmstaendeFormSet(daten, prefix="um"),
        "kurztexte": lambda daten: KurztexteFormSet(daten, prefix="kt"),
    }
    welches = next((name for name in teile if name in request.POST), None)
    formulare = {name: bauen(request.POST if name == welches else None)
                 for name, bauen in teile.items()}  # fmt: skip
    if request.method == "POST" and welches and formulare[welches].is_valid():
        formulare[welches].save()
        messages.success(request, "Gespeichert.")
        return redirect("touren:einrichten")
    return render(request, "touren/einrichten.html", {
        "form": formulare["einrichten"], "gruppen": formulare["warengruppen"],
        "umstaende": formulare["umstaende"],
        "kurztexte": formulare["kurztexte"],
        "fahrzeuge": Fahrzeug.objects.filter(verkauft_am=None).annotate(
            papiere=Count("dokumente")
        ),
        "verkauft": Fahrzeug.objects.exclude(verkauft_am=None).annotate(
            papiere=Count("dokumente")
        ).order_by("-verkauft_am", "name"),
        "darf_einstellen": rollen.hat_recht(request.user, "einstellungen.touren"),
    })  # fmt: skip
