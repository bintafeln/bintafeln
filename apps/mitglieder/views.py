"""Mitglieder (ADR 0046): Liste, Anlegen, Bearbeiten, Beiträge je Jahr, offene Beiträge."""

import csv
import io
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.db.models.functions import Length
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import listen, listenauswahl, papierkorb
from apps.konten import rollen
from apps.mitglieder.forms import MitgliederEinstellungenForm, MitgliedForm
from apps.mitglieder.models import Mitglied, MitgliederEinstellungen, nummer_verbraucht


def _jahr(request) -> int:
    wert = request.GET.get("jahr", "")
    return int(wert) if wert.isdigit() and 1990 < int(wert) < 2200 else timezone.localdate().year


def _jahre():
    erstes = Mitglied.objects.order_by("eintritt").values_list("eintritt__year", flat=True).first()
    heute = timezone.localdate().year
    return list(range(heute, min(erstes or heute, heute) - 1, -1))


def _zeilen(mitglieder, jahr: int):
    anteilig = MitgliederEinstellungen.laden().anteilig
    zeilen = []
    for m in mitglieder:
        soll, gezahlt = m.soll(jahr, anteilig), m.gezahlt(jahr)
        zeilen.append(
            {"m": m, "soll": soll, "gezahlt": gezahlt, "offen": max(soll - gezahlt, Decimal("0"))}
        )
    return zeilen


# Spalten zum Zu-/Abwählen je Person (Nr. öffnet das Mitglied und bleibt immer sichtbar);
# die Beitragsspalten gibt es nur, wenn Beiträge eingeschaltet sind.
SPALTEN_FEST = {"nummer"}


def _spalten(beitraege) -> list[tuple[str, str]]:
    spalten = [("nummer", "Nr."), ("name", "Name"), ("art", "Art"), ("eintritt", "Eintritt")]
    if beitraege:
        spalten += [("soll", "Soll"), ("gezahlt", "gezahlt"), ("offen", "offen")]
    return spalten


@rollen.recht_erforderlich("mitglieder.sehen")
def liste(request):
    jahr = _jahr(request)
    stand = request.GET.get("stand", "aktiv")
    # Nummern wie Zahlen sortieren: 1, 2, 3 … 10 statt 1, 10, 11 … 2
    mitglieder = Mitglied.objects.select_related("adresse").order_by(Length("nummer"), "nummer")
    heute = timezone.localdate()
    if stand == "aktiv":
        mitglieder = mitglieder.filter(Q(austritt__isnull=True) | Q(austritt__gte=heute))
    elif stand == "ausgetreten":
        mitglieder = mitglieder.filter(austritt__lt=heute)
    q = request.GET.get("q", "").strip()
    if q:
        mitglieder = mitglieder.filter(
            Q(nummer__icontains=q) | Q(adresse__organisation__icontains=q)
            | Q(adresse__nachname__icontains=q) | Q(adresse__vorname__icontains=q)
        )  # fmt: skip
    if request.GET.get("csv"):
        mitglieder = listenauswahl.filtern(request, mitglieder)
    beitraege = MitgliederEinstellungen.mit_beitraegen()
    if beitraege:
        zeilen = _zeilen(mitglieder, jahr)
        if request.GET.get("nur_offen"):
            zeilen = [z for z in zeilen if z["offen"] > 0]
    else:
        zeilen = [{"m": m} for m in mitglieder]
    # Spalten wie Zahlen/Namen sortieren; Beitragsspalten nur, wenn es Beiträge gibt.
    schluessel = {
        "nummer": lambda z: (len(z["m"].nummer), z["m"].nummer),
        "name": lambda z: z["m"].adresse.name.lower(),
        "art": lambda z: z["m"].art,
        "eintritt": lambda z: z["m"].eintritt,
    }
    if beitraege:
        schluessel |= {f: (lambda z, f=f: z[f]) for f in ("soll", "gezahlt", "offen")}
    zeilen, sort = listen.sortieren_liste(zeilen, request.GET.get("sort", ""), schluessel, "nummer")
    if request.GET.get("csv"):
        return _csv(zeilen, jahr, beitraege)
    alle = Mitglied.objects.all()
    kennzahlen = {
        "mitglieder": sum(1 for m in alle if m.ist_mitglied(heute)),
        "eintritte": alle.filter(eintritt__year=jahr).count(),
        "austritte": alle.filter(austritt__year=jahr).count(),
    }
    if beitraege:
        for feld in ("soll", "gezahlt", "offen"):
            kennzahlen[feld] = sum(z[feld] for z in zeilen)
    spalten = _spalten(beitraege)
    abfrage = request.GET.copy()
    abfrage.pop("seite", None)
    return render(request, "mitglieder/liste.html", {
        "zeilen": zeilen, "jahr": jahr, "jahre": _jahre(), "k": kennzahlen, "beitraege": beitraege,
        "sort": sort,
        "sichtbar": listen.sichtbare_spalten(request.user, "mitglieder",
                                             [k for k, _ in spalten], SPALTEN_FEST),
        "spalten_wahl": listen.spalten_wahl(request.user, "mitglieder", spalten, SPALTEN_FEST),
        "abfrage": abfrage.urlencode(),
        "filter": {"stand": stand, "q": q, "nur_offen": request.GET.get("nur_offen", "")},
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("mitglieder.sehen")
def spalten(request):
    """Speichert, welche Spalten diese Person in der Mitgliederliste sieht."""
    spalten = _spalten(MitgliederEinstellungen.mit_beitraegen())
    listen.spalten_speichern(request.user, "mitglieder", request.POST.getlist("spalte"),
                             spalten, SPALTEN_FEST)  # fmt: skip
    zurueck = QueryDict(request.POST.get("zurueck", "")).urlencode()
    ziel = reverse("mitglieder:liste")
    return redirect(f"{ziel}?{zurueck}" if zurueck else ziel)


def _csv(zeilen, jahr, beitraege):
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    kopf = ["Nummer", "Name", "Anschrift", "E-Mail", "Art", "Eintritt", "Austritt"]
    if beitraege:
        kopf += ["Jahresbeitrag", "Zahlungsart", f"Soll {jahr}", f"Gezahlt {jahr}", f"Offen {jahr}"]
    w.writerow(kopf)

    def euro(betrag):
        return f"{betrag:.2f}".replace(".", ",")

    for z in zeilen:
        m = z["m"]
        zeile = [
            m.nummer,
            m.adresse.name,
            ", ".join(m.adresse.anschrift_zeilen[1:]),
            m.adresse.email,
            m.art,
            f"{m.eintritt:%d.%m.%Y}",
            f"{m.austritt:%d.%m.%Y}" if m.austritt else "",
        ]
        if beitraege:
            zeile += [euro(m.jahresbeitrag), m.zahlungsart, euro(z["soll"]), euro(z["gezahlt"]),
                      euro(z["offen"])]  # fmt: skip
        w.writerow(zeile)
    antwort = HttpResponse("﻿" + puffer.getvalue(), content_type="text/csv")
    antwort["Content-Disposition"] = f'attachment; filename="mitglieder-{jahr}.csv"'
    return antwort


@rollen.recht_erforderlich("mitglieder.sehen")
def mitglied(request, pk):
    m = get_object_or_404(Mitglied.objects.select_related("adresse", "benutzer"), pk=pk)
    e = MitgliederEinstellungen.laden()
    if not e.beitraege:
        return render(request, "mitglieder/mitglied.html", {"m": m, "mit_beitraegen": False})
    anteilig = e.anteilig
    jahre = range(timezone.localdate().year, m.eintritt.year - 1, -1)
    beitraege = []
    for jahr in jahre:
        soll, gezahlt = m.soll(jahr, anteilig), m.gezahlt(jahr)
        if soll or gezahlt:
            beitraege.append({"jahr": jahr, "soll": soll, "gezahlt": gezahlt,
                              "offen": max(soll - gezahlt, Decimal("0"))})  # fmt: skip
    zahlungen = m.adresse.spenden.filter(mitgliedsbeitrag=True)[:30]
    return render(request, "mitglieder/mitglied.html", {
        "m": m, "beitraege": beitraege, "zahlungen": zahlungen, "mit_beitraegen": True,
    })  # fmt: skip


@never_cache
@rollen.recht_erforderlich("mitglieder.bearbeiten")
def bearbeiten(request, pk=None):
    if pk:
        m = get_object_or_404(Mitglied, pk=pk)
        initial = {}
    else:
        e = MitgliederEinstellungen.laden()
        m = Mitglied(eintritt=timezone.localdate(), jahresbeitrag=e.standard_beitrag)
        initial = {"nummer": e.naechste_nummer}
        if request.GET.get("adresse", "").isdigit():
            initial["adresse"] = request.GET["adresse"]
    form = MitgliedForm(request.POST or None, instance=m, initial=initial)
    if request.method == "POST" and form.is_valid():
        m = form.save()
        nummer_verbraucht(m.nummer)
        messages.success(request, f"Mitglied {m.nummer} ({m.adresse.name}) gespeichert.")
        return redirect("mitglieder:mitglied", pk=m.pk)
    return render(request, "mitglieder/bearbeiten.html", {"form": form, "m": m})


@require_POST
@rollen.recht_erforderlich("mitglieder.bearbeiten")
def loeschen(request, pk):
    m = get_object_or_404(Mitglied, pk=pk)
    adresse = m.adresse_id
    papierkorb.loeschen(request.user, "Mitgliedschaft", str(m), m, recht="mitglieder.bearbeiten")
    messages.success(request, "Mitgliedschaft in den Papierkorb gelegt. Adresse und Zahlungen "
                              "bleiben erhalten.")  # fmt: skip
    return redirect("adressen:adresse", pk=adresse)


@never_cache
@rollen.recht_erforderlich("einstellungen.mitglieder")
def einstellungen(request):
    form = MitgliederEinstellungenForm(request.POST or None,
                                       instance=MitgliederEinstellungen.laden())  # fmt: skip
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("mitglieder:einstellungen")
    return render(request, "mitglieder/einstellungen.html", {"form": form})
