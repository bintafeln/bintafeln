from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.abrechnung import ablauf
from apps.abrechnung.forms import EinreichenForm, EinstellungenForm, PostenForm, RueckgabeForm
from apps.abrechnung.models import AbrechnungEinstellungen, Monatsabrechnung, Posten
from apps.core import privatdateien
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle

fuehren_oder_pruefen = rollen.recht_erforderlich("abrechnung.fuehren", "abrechnung.pruefen")
pruefen = rollen.recht_erforderlich("abrechnung.pruefen")


def _stelle(request, pk) -> Ausgabestelle:
    stelle = get_object_or_404(Ausgabestelle, pk=pk)
    if not (ablauf.darf_pruefen(request.user) or ablauf.darf_fuehren(request.user, stelle)):
        raise PermissionDenied("Sie dürfen nur die Abrechnung Ihrer eigenen Ausgabestelle sehen.")
    return stelle


def _zur_abrechnung(abr) -> HttpResponse:
    return redirect("abrechnung:monat", abr.stelle_id, f"{abr.monat:%Y-%m}")


@never_cache
@fuehren_oder_pruefen
def uebersicht(request):
    """Ausgabestelle: gleich zur eigenen Abrechnung. Büro: alle Ausgabestellen eines Monats."""
    monat = ablauf.monat_lesen(request.GET.get("monat"), timezone.localdate())
    stellen = ablauf.stellen_fuer(request.user)
    if not ablauf.darf_pruefen(request.user):
        if len(stellen) == 1:
            return redirect("abrechnung:monat", stellen[0].pk, f"{monat:%Y-%m}")
        return render(request, "abrechnung/uebersicht.html", {"stellen": stellen,
                      "monat": monat, "zeilen": None})  # fmt: skip
    vorhanden = {a.stelle_id: a for a in Monatsabrechnung.objects.filter(monat=monat)}
    zeilen = []
    for s in stellen:
        abr = vorhanden.get(s.pk) or Monatsabrechnung(stelle=s, monat=monat)
        zeilen.append(
            {
                "stelle": s,
                "abr": abr,
                **ablauf.zahlen(abr),
                "quittungen": abr.posten.exclude(quittung="").count() if abr.pk else 0,
            }
        )
    return render(request, "abrechnung/uebersicht.html", {
        "monat": monat, "zeilen": zeilen, "name": ablauf.monatsname(monat),
        "zurueck": f"{ablauf.verschieben(monat, -1):%Y-%m}",
        "vor": f"{ablauf.verschieben(monat, 1):%Y-%m}",
    })  # fmt: skip


@never_cache
@fuehren_oder_pruefen
def monat(request, stelle, monat):
    stelle = _stelle(request, stelle)
    abr = ablauf.holen(stelle, ablauf.monat_lesen(monat, timezone.localdate()))
    darf_fuehren = ablauf.darf_fuehren(request.user, stelle)
    form = PostenForm(
        request.POST or None,
        request.FILES or None,
        initial={"datum": min(timezone.localdate(), ablauf.monatsende(abr.monat))},
    )
    if request.method == "POST":
        if not darf_fuehren:
            raise PermissionDenied
        if form.is_valid():
            daten = {k: form.cleaned_data[k] for k in PostenForm.Meta.fields}
            try:
                ablauf.posten_anlegen(abr, daten, form.quittung, request.user)
            except (ablauf.AbrechnungFehler, privatdateien.DateiFehler) as fehler:
                messages.error(request, str(fehler))
            else:
                messages.success(request, "Ausgabe gespeichert.")
                return _zur_abrechnung(abr)
    return render(request, "abrechnung/monat.html", {
        "abr": abr, "stelle": stelle, "name": ablauf.monatsname(abr.monat), "form": form,
        "z": ablauf.zahlen(abr), "posten": abr.posten.all(), "darf_fuehren": darf_fuehren,
        "darf_pruefen": ablauf.darf_pruefen(request.user),
        "einreichen_form": EinreichenForm(initial={"anmerkung": abr.anmerkung}),
        "rueckgabe_form": RueckgabeForm(), "stellen": ablauf.stellen_fuer(request.user),
        "zurueck": f"{ablauf.verschieben(abr.monat, -1):%Y-%m}",
        "vor": f"{ablauf.verschieben(abr.monat, 1):%Y-%m}",
    })  # fmt: skip


@require_POST
@fuehren_oder_pruefen
def aktion(request, pk, was):
    abr = get_object_or_404(Monatsabrechnung, pk=pk)
    _stelle(request, abr.stelle_id)
    try:
        if was == "einreichen":
            if not ablauf.darf_fuehren(request.user, abr.stelle):
                raise PermissionDenied
            form = EinreichenForm(request.POST)
            form.is_valid()
            ablauf.einreichen(abr, request.user, form.cleaned_data.get("anmerkung", ""))
            messages.success(request, "Abrechnung eingereicht. Das Büro prüft sie.")
        elif was in ("bestaetigen", "zurueckgeben"):
            if not ablauf.darf_pruefen(request.user):
                raise PermissionDenied
            if was == "bestaetigen":
                ablauf.bestaetigen(abr, request.user)
                messages.success(request, "Abrechnung bestätigt.")
            else:
                ablauf.zurueckgeben(abr, request.user, request.POST.get("grund", ""))
                messages.success(request, "Abrechnung an die Ausgabestelle zurückgegeben.")
        else:
            raise Http404
    except ablauf.AbrechnungFehler as fehler:
        messages.error(request, str(fehler))
    return _zur_abrechnung(abr)


@require_POST
@fuehren_oder_pruefen
def posten_loeschen(request, pk):
    posten = get_object_or_404(Posten.objects.select_related("abrechnung__stelle"), pk=pk)
    if not ablauf.darf_fuehren(request.user, posten.abrechnung.stelle):
        raise PermissionDenied
    try:
        ablauf.posten_loeschen(posten)
    except ablauf.AbrechnungFehler as fehler:
        messages.error(request, str(fehler))
    else:
        messages.success(request, "Ausgabe gelöscht.")
    return _zur_abrechnung(posten.abrechnung)


@never_cache
@fuehren_oder_pruefen
def quittung(request, pk):
    posten = get_object_or_404(Posten.objects.select_related("abrechnung__stelle"), pk=pk)
    _stelle(request, posten.abrechnung.stelle_id)
    inhalt = privatdateien.lesen(Posten.ORDNER, posten.quittung)
    if inhalt is None:
        raise Http404("Keine lesbare Quittung.")
    antwort = HttpResponse(inhalt, content_type=posten.quittung_typ or "application/octet-stream")
    antwort["Content-Disposition"] = f'inline; filename="{ablauf.quittung_dateiname(posten)}"'
    antwort["X-Content-Type-Options"] = "nosniff"
    return antwort


@never_cache
@fuehren_oder_pruefen
def als_pdf(request, pk):
    abr = get_object_or_404(Monatsabrechnung.objects.select_related("stelle"), pk=pk)
    _stelle(request, abr.stelle_id)
    return pdf_antwort(ablauf.pdf(abr), f"abrechnung-{ablauf._sicher(abr.stelle.name)}-"
                                        f"{abr.monat:%Y-%m}.pdf")  # fmt: skip


@never_cache
@pruefen
def quittungen(request, monat):
    """ZIP mit allen Quittungen eines Monats, auf Wunsch nur einer Ausgabestelle."""
    beginn = ablauf.monat_lesen(monat, timezone.localdate())
    abrechnungen = Monatsabrechnung.objects.filter(monat=beginn).select_related("stelle")
    if request.GET.get("stelle", "").isdigit():
        abrechnungen = abrechnungen.filter(stelle_id=int(request.GET["stelle"]))
    inhalt, anzahl = ablauf.quittungen_zip(abrechnungen)
    if not anzahl:
        messages.info(request, "Für diese Auswahl gibt es keine Quittungen.")
        return redirect(f"{reverse('abrechnung:uebersicht')}?monat={beginn:%Y-%m}")
    antwort = HttpResponse(inhalt, content_type="application/zip")
    antwort["Content-Disposition"] = f'attachment; filename="quittungen-{beginn:%Y-%m}.zip"'
    return antwort


@never_cache
@pruefen
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=AbrechnungEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen der Abrechnung gespeichert.")
        return redirect("abrechnung:einstellungen")
    return render(request, "abrechnung/einstellungen.html", {"form": form})
