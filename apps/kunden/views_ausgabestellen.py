"""Ausgabestellen mit Anschrift, Zeiten, Ansprechpartnern und Karte (ADR 0048)."""

from urllib.parse import quote_plus

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.konten import rollen
from apps.kunden.forms_bearbeiten import AusgabestelleForm, KontakteFormset, ZeitenFormset
from apps.kunden.models import Ausgabestelle, Haushalt


def karten_links(stelle: Ausgabestelle) -> dict | None:
    """Links zu Google Maps. Die eingebettete Karte lädt erst nach Klick (Datenschutz)."""
    if not stelle.anschrift:
        return None
    suche = quote_plus(f"{stelle.anschrift}")
    return {
        "oeffnen": f"https://www.google.com/maps/search/?api=1&query={suche}",
        "einbetten": f"https://www.google.com/maps?q={suche}&output=embed",
    }


@rollen.recht_erforderlich("kunden.liste")
def liste(request):
    stellen = Ausgabestelle.objects.prefetch_related("zeiten").order_by("-aktiv", "name")
    return render(request, "kunden/ausgabestellen.html", {"stellen": stellen})


@rollen.recht_erforderlich("kunden.liste")
def ausgabestelle(request, pk):
    stelle = get_object_or_404(
        Ausgabestelle.objects.prefetch_related("zeiten", "kontakte__benutzer"), pk=pk
    )
    aktiv = Count("haushalte", filter=~Q(haushalte__status=Haushalt.Status.BEENDET))
    gruppen = stelle.kundengruppe_set.filter(aktiv=True).annotate(belegt=aktiv).order_by("name")
    return render(request, "kunden/ausgabestelle.html", {
        "s": stelle, "gruppen": gruppen, "karte": karten_links(stelle),
    })  # fmt: skip


@rollen.recht_erforderlich("einstellungen.listen")
def bearbeiten(request, pk=None):
    stelle = get_object_or_404(Ausgabestelle, pk=pk) if pk else Ausgabestelle()
    daten = request.POST or None
    form = AusgabestelleForm(daten, instance=stelle)
    zeiten = ZeitenFormset(daten, instance=stelle, prefix="z")
    kontakte = KontakteFormset(daten, instance=stelle, prefix="k")
    if request.method == "POST" and all([form.is_valid(), zeiten.is_valid(), kontakte.is_valid()]):
        with transaction.atomic():
            stelle = form.save()
            zeiten.instance = kontakte.instance = stelle
            zeiten.save()
            kontakte.save()
        messages.success(request, f"Ausgabestelle „{stelle}“ gespeichert.")
        return redirect("kunden:ausgabestelle", pk=stelle.pk)
    return render(request, "kunden/ausgabestelle_bearbeiten.html", {
        "s": stelle, "form": form, "zeiten": zeiten, "kontakte": kontakte,
    })  # fmt: skip
