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
from apps.ausgabe import stelle as stelle_wahl
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
    eingabe = request.GET.get("monat", "")
    monat = ablauf.monat_aus_text(eingabe)
    if monat is None:
        # Unlesbare Eingabe: beim bisherigen Monat bleiben und sagen, wie es richtig heißt
        monat = ablauf.monat_lesen(request.GET.get("bisher"), timezone.localdate())
        if eingabe.strip():
            messages.error(request, f"„{eingabe.strip()[:20]}“ ist kein Monat. Bitte als MMJJ "
                                    "eingeben, z. B. 1126 für November 2026.")  # fmt: skip
    stellen = ablauf.stellen_fuer(request.user)
    if not ablauf.darf_pruefen(request.user):
        # die eine eigene oder die oben im Menü gewählte Ausgabestelle (ADR 0067)
        gewaehlt = stelle_wahl.aktuelle(request.user)
        ziel = stellen[0] if len(stellen) == 1 else (gewaehlt if gewaehlt in stellen else None)
        if ziel:
            return redirect("abrechnung:monat", ziel.pk, f"{monat:%Y-%m}")
        return render(request, "abrechnung/uebersicht.html", {"stellen": stellen,
                      "monat": monat, "zeilen": None})  # fmt: skip
    nur_eingereichte = request.GET.get("status") == "eingereicht"
    if nur_eingereichte:  # über alle Monate: was wartet auf die Prüfung?
        paare = [(a.stelle, a) for a in ablauf.eingereichte()]
    else:
        vorhanden = {a.stelle_id: a for a in ablauf.im_monat(monat)}
        paare = [(s, vorhanden.get(s.pk) or Monatsabrechnung(stelle=s, monat=monat))
                 for s in stellen]  # fmt: skip
    zeilen = []
    for s, abr in paare:
        zeilen.append(
            {
                "stelle": s,
                "abr": abr,
                "zeitraum": ablauf.zeitraum_kurz(abr) if abr.monate > 1 else "",
                "kurz": ablauf.zeitraum_kurz(abr),
                **ablauf.zahlen(abr),
                "quittungen": abr.posten.exclude(quittung="").count() if abr.pk else 0,
            }
        )
    return render(request, "abrechnung/uebersicht.html", {
        "monat": monat, "zeilen": zeilen, "name": ablauf.monatsname(monat),
        "mmjj": ablauf.mmjj(monat), "nur_eingereichte": nur_eingereichte,
        "wartend": ablauf.eingereichte().count(),
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
        initial={"datum": min(timezone.localdate(), ablauf.monatsende(abr.ende))},
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
        "abr": abr, "stelle": stelle, "name": ablauf.zeitraum_name(abr), "form": form,
        "kurz": ablauf.zeitraum_kurz(abr),
        "von": ablauf.monatsname(abr.monat), "zeitraeume": ablauf.zeitraeume(abr),
        "z": ablauf.zahlen(abr), "posten": abr.posten.all(), "darf_fuehren": darf_fuehren,
        "quittungen": abr.posten.exclude(quittung="").count(),
        "darf_pruefen": ablauf.darf_pruefen(request.user),
        "einreichen_form": EinreichenForm(initial={"anmerkung": abr.anmerkung}),
        "rueckgabe_form": RueckgabeForm(), "stellen": ablauf.stellen_fuer(request.user),
        "zurueck": f"{ablauf.verschieben(abr.monat, -1):%Y-%m}",
        "vor": f"{ablauf.verschieben(abr.ende, 1):%Y-%m}",
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
        elif was in ("zuruecknehmen", "zeitraum"):
            if not ablauf.darf_fuehren(request.user, abr.stelle):
                raise PermissionDenied
            if was == "zuruecknehmen":
                ablauf.zuruecknehmen(abr)
                messages.success(request, "Die Abrechnung ist wieder offen. Bitte nach den "
                                          "Änderungen erneut einreichen.")  # fmt: skip
            else:
                monate = request.POST.get("monate", "")
                ablauf.zeitraum_aendern(abr, int(monate) if monate.isdigit() else 0)
                abr.refresh_from_db()
                messages.success(request, f"Zeitraum: {ablauf.zeitraum_name(abr)}.")
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


@never_cache
@fuehren_oder_pruefen
def posten_bearbeiten(request, pk):
    """Eine eingetragene Ausgabe ändern, solange die Abrechnung nicht abgeschickt ist."""
    posten = get_object_or_404(Posten.objects.select_related("abrechnung__stelle"), pk=pk)
    abr = posten.abrechnung
    if not ablauf.darf_fuehren(request.user, abr.stelle):
        raise PermissionDenied
    if not abr.offen:  # auch der direkte Aufruf der Adresse ist gesperrt
        messages.error(request, ablauf.ABGESCHICKT)
        return _zur_abrechnung(abr)
    form = PostenForm(request.POST or None, request.FILES or None, instance=posten)
    if request.method == "POST" and form.is_valid():
        daten = {k: form.cleaned_data[k] for k in PostenForm.Meta.fields}
        try:
            ablauf.posten_aendern(posten, daten, form.quittung, request.user)
        except (ablauf.AbrechnungFehler, privatdateien.DateiFehler) as fehler:
            messages.error(request, str(fehler))
            posten.refresh_from_db()
            if not posten.abrechnung.offen:
                return _zur_abrechnung(abr)
        else:
            messages.success(request, "Ausgabe geändert.")
            return _zur_abrechnung(abr)
    return render(request, "abrechnung/posten.html", {
        "form": form, "posten": posten, "abr": abr, "stelle": abr.stelle,
        "kurz": ablauf.zeitraum_kurz(abr),
    })  # fmt: skip


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
    art = "attachment" if request.GET.get("herunterladen") else "inline"
    antwort["Content-Disposition"] = f'{art}; filename="{ablauf.quittung_dateiname(posten)}"'
    antwort["X-Content-Type-Options"] = "nosniff"
    return antwort


@never_cache
@fuehren_oder_pruefen
def als_pdf(request, pk):
    abr = get_object_or_404(Monatsabrechnung.objects.select_related("stelle"), pk=pk)
    _stelle(request, abr.stelle_id)
    return pdf_antwort(ablauf.pdf(abr), f"abrechnung-{ablauf._sicher(abr.stelle.name)}-"
                                        f"{ablauf.mmjj(abr.monat)}.pdf")  # fmt: skip


@never_cache
@fuehren_oder_pruefen
def quittungen(request, monat):
    """ZIP mit allen Quittungen eines Monats, auf Wunsch nur einer Ausgabestelle. Ohne das Recht
    zu prüfen nur für eine eigene Ausgabestelle."""
    beginn = ablauf.monat_lesen(monat, timezone.localdate())
    abrechnungen = ablauf.im_monat(beginn).select_related("stelle")
    if request.GET.get("stelle", "").isdigit():
        stelle = _stelle(request, int(request.GET["stelle"]))
        abrechnungen = abrechnungen.filter(stelle=stelle)
    elif not ablauf.darf_pruefen(request.user):
        raise PermissionDenied
    inhalt, anzahl = ablauf.quittungen_zip(abrechnungen)
    if not anzahl:
        messages.info(request, "Für diese Auswahl gibt es keine Quittungen.")
        return redirect(f"{reverse('abrechnung:uebersicht')}?monat={beginn:%Y-%m}")
    teil = f"-{ablauf._sicher(abrechnungen[0].stelle.name)}" if "stelle" in request.GET else ""
    antwort = HttpResponse(inhalt, content_type="application/zip")
    antwort["Content-Disposition"] = (
        f'attachment; filename="quittungen{teil}-{ablauf.mmjj(beginn)}.zip"')  # fmt: skip
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
