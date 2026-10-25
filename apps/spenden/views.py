"""Spenden und Zuwendungsbestätigungen (ADR 0045)."""

import csv
import io

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.adressen.models import Adresse
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.spenden import bestaetigung as bst
from apps.spenden.forms import SpendeForm, SpendenEinstellungenForm
from apps.spenden.models import Spende, SpendenEinstellungen, Zuwendungsbestaetigung


def _jahr(request) -> int:
    wert = request.GET.get("jahr", "")
    return int(wert) if wert.isdigit() and 1990 < int(wert) < 2200 else timezone.localdate().year


def _jahre():
    jahre = {d.year for d in Spende.objects.dates("datum", "year")}
    jahre.add(timezone.localdate().year)
    return sorted(jahre, reverse=True)


@rollen.recht_erforderlich("spenden.sehen")
def liste(request):
    jahr = _jahr(request)
    spenden = Spende.objects.filter(datum__year=jahr).select_related("adresse", "bestaetigung")
    art = request.GET.get("art", "")
    if art in Spende.Art.values:
        spenden = spenden.filter(art=art)
    q = request.GET.get("q", "").strip()
    if q:
        spenden = spenden.filter(
            Q(adresse__organisation__icontains=q) | Q(adresse__nachname__icontains=q)
            | Q(adresse__vorname__icontains=q) | Q(beschreibung__icontains=q)
            | Q(zweck__icontains=q)
        )  # fmt: skip
    if request.GET.get("csv"):
        return _csv(spenden, jahr)
    summen = spenden.aggregate(
        geld=Sum("betrag", filter=Q(art=Spende.Art.GELD)),
        sach=Sum("betrag", filter=Q(art=Spende.Art.SACH)),
        anzahl=Count("pk"), spender=Count("adresse", distinct=True),
    )  # fmt: skip
    je_monat = (spenden.filter(art=Spende.Art.GELD).values_list("datum__month")
                .annotate(s=Sum("betrag")).order_by("datum__month"))  # fmt: skip
    return render(request, "spenden/liste.html", {
        "seite": Paginator(spenden, 50).get_page(request.GET.get("seite")),
        "jahr": jahr, "jahre": _jahre(), "filter": {"art": art, "q": q}, "summen": summen,
        "je_monat": list(je_monat), "arten": Spende.Art.choices,
    })  # fmt: skip


def _csv(spenden, jahr):
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow(
        [
            "Datum",
            "Art",
            "Spender",
            "PLZ",
            "Ort",
            "Betrag/Wert",
            "Mitgliedsbeitrag",
            "Zahlungsweg",
            "Bezeichnung",
            "Menge",
            "Einheit",
            "Zweck",
            "Bestätigung",
        ]
    )
    for s in spenden:
        w.writerow([f"{s.datum:%d.%m.%Y}", s.get_art_display(), s.adresse.name, s.adresse.plz,
                    s.adresse.ort, f"{s.betrag:.2f}".replace(".", ",") if s.betrag else "",
                    "ja" if s.mitgliedsbeitrag else "", s.zahlungsweg, s.beschreibung,
                    s.menge or "", s.einheit, s.zweck,
                    s.bestaetigung.nummer if s.bestaetigt else ""])  # fmt: skip
    antwort = HttpResponse("﻿" + puffer.getvalue(), content_type="text/csv")
    antwort["Content-Disposition"] = f'attachment; filename="spenden-{jahr}.csv"'
    return antwort


@never_cache
@rollen.recht_erforderlich("spenden.erfassen")
def bearbeiten(request, pk=None):
    s = get_object_or_404(Spende, pk=pk) if pk else Spende()
    if s.bestaetigt:
        messages.error(request, f"Diese Spende ist mit Zuwendungsbestätigung Nr. "
                                f"{s.bestaetigung.nummer} bestätigt. Zum Ändern die Bestätigung "
                                "zuerst stornieren.")  # fmt: skip
        return redirect("spenden:bestaetigungen")
    initial = {}
    if not pk and request.GET.get("adresse", "").isdigit():
        initial["adresse"] = request.GET["adresse"]
    form = SpendeForm(request.POST or None, instance=s, initial=initial)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        if not s.eingetragen_von:
            s.eingetragen_von = request.user.get_username()
        s.save()
        messages.success(request, f"{s} von {s.adresse.name} gespeichert.")
        if request.POST.get("weiter"):
            return redirect(reverse("spenden:neu"))
        return redirect("adressen:adresse", pk=s.adresse_id)
    return render(request, "spenden/bearbeiten.html", {"form": form, "s": s})


@require_POST
@rollen.recht_erforderlich("spenden.erfassen")
def loeschen(request, pk):
    s = get_object_or_404(Spende, pk=pk)
    if s.bestaetigt:
        messages.error(request, "Bestätigte Spenden lassen sich nicht löschen.")
    else:
        s.delete()
        messages.success(request, "Spende gelöscht.")
    return redirect("adressen:adresse", pk=s.adresse_id)


@never_cache
@rollen.recht_erforderlich("spenden.bestaetigen")
def bestaetigungen(request):
    jahr = _jahr(request)
    e = SpendenEinstellungen.laden()
    ausgestellt = Zuwendungsbestaetigung.objects.filter(
        ausgestellt_am__year=jahr).select_related("adresse")  # fmt: skip
    return render(request, "spenden/bestaetigungen.html", {
        "neu_pdf": request.session.pop("spenden_neu", ""),
        "jahr": jahr, "jahre": _jahre(), "offen": bst.jahresliste(jahr),
        "ausgestellt": ausgestellt, "fehlt": e.fehlende_angaben(),
        "sachspenden": Spende.objects.filter(art=Spende.Art.SACH, datum__year=jahr)
        .exclude(bestaetigung__isnull=False, bestaetigung__storniert_am__isnull=True)
        .select_related("adresse"),
    })  # fmt: skip


def _pdf_link(liste) -> str:
    return reverse("spenden:pdf") + "?nummern=" + ",".join(str(b.nummer) for b in liste)


@require_POST
@rollen.recht_erforderlich("spenden.bestaetigen")
def ausstellen(request):
    jahr = _jahr(request)
    von = request.user.get_username()
    try:
        if request.POST.get("spende", "").isdigit():
            liste = [bst.sach_ausstellen(get_object_or_404(Spende, pk=request.POST["spende"]), von)]
        elif request.POST.get("adresse", "").isdigit():
            a = get_object_or_404(Adresse, pk=request.POST["adresse"])
            liste = [bst.geld_ausstellen(a, jahr, von)]
        else:
            liste = [bst.geld_ausstellen(a, jahr, von) for a, _, _ in bst.jahresliste(jahr)]
    except bst.BestaetigungsFehler as fehler:
        messages.error(request, str(fehler))
        return redirect(f"{reverse('spenden:bestaetigungen')}?jahr={jahr}")
    request.session["spenden_neu"] = _pdf_link(liste)
    endung = "en" if len(liste) != 1 else ""
    messages.success(request, f"{len(liste)} Zuwendungsbestätigung{endung} ausgestellt.")
    return redirect(f"{reverse('spenden:bestaetigungen')}?jahr={jahr}")


@rollen.recht_erforderlich("spenden.bestaetigen")
def pdf(request):
    nummern = [int(n) for n in request.GET.get("nummern", "").split(",") if n.isdigit()]
    liste = list(Zuwendungsbestaetigung.objects.filter(nummer__in=nummern).order_by("nummer"))
    if not liste:
        raise Http404
    name = f"zuwendungsbestaetigung-{liste[0].nummer}" + (
        f"-bis-{liste[-1].nummer}" if len(liste) > 1 else "")  # fmt: skip
    return pdf_antwort(bst.pdf(liste), f"{name}.pdf")


@require_POST
@rollen.recht_erforderlich("spenden.bestaetigen")
def stornieren(request, nummer):
    b = get_object_or_404(Zuwendungsbestaetigung, nummer=nummer)
    bst.stornieren(b, request.user.get_username())
    messages.success(request, f"Zuwendungsbestätigung Nr. {nummer} storniert. Die Spenden lassen "
                              "sich neu bestätigen.")  # fmt: skip
    return redirect(f"{reverse('spenden:bestaetigungen')}?jahr={b.ausgestellt_am.year}")


@never_cache
@rollen.recht_erforderlich("einstellungen.spenden")
def einstellungen(request):
    form = SpendenEinstellungenForm(request.POST or None, instance=SpendenEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("spenden:einstellungen")
    return render(request, "spenden/einstellungen.html", {"form": form})
