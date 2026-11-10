"""Ausgabestellen mit Anschrift, Zeiten, Ansprechpartnern und Karte (ADR 0048)."""

import datetime as dt
from urllib.parse import quote_plus

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.konten import rollen
from apps.kunden import verlegung
from apps.kunden.forms_bearbeiten import AusgabestelleForm, KontakteFormset, ZeitenFormset
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe


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


@rollen.recht_erforderlich("kunden.bearbeiten")
def verlegen(request, pk):
    """Kunden einer (schließenden) Ausgabestelle auf andere Kundengruppen verteilen: je Haushalt
    eine neue Kundengruppe und ein gemeinsamer Stichtag. Am Stichtag führt die tägliche Regel die
    Wechsel aus (ADR 0118)."""
    stelle = get_object_or_404(Ausgabestelle, pk=pk)
    haushalte = list(
        Haushalt.objects.filter(
            kundengruppe__ausgabestelle=stelle,
            kundengruppe__aktiv=True,
            status=Haushalt.Status.AKTIV,
        )
        .select_related("kundengruppe")
        .prefetch_related("personen")
        .order_by("kundengruppe__name", "kundennummer")
    )
    ziele = list(
        Kundengruppe.objects.filter(aktiv=True)
        .exclude(ausgabestelle=stelle)
        .select_related("ausgabestelle")
        .order_by("ausgabestelle__name", "name")
    )
    offen = {w.haushalt_id: w for w in [verlegung.offener(h) for h in haushalte] if w}
    if request.method == "POST":
        try:
            ab = dt.date.fromisoformat(request.POST.get("ab", ""))
        except ValueError:
            messages.error(request, "Bitte einen Stichtag (Datum) angeben.")
            return redirect("kunden:ausgabestelle_verlegen", pk=stelle.pk)
        gueltig = {str(z.pk): z for z in ziele}
        geplant = entfernt = 0
        for h in haushalte:
            wahl = request.POST.get(f"ziel_{h.pk}", "")
            if wahl in gueltig:
                verlegung.planen(h, gueltig[wahl], ab, request.user.get_username())
                geplant += 1
            elif h.pk in offen:  # leer gewählt: vorhandenen Plan zurücknehmen
                verlegung.entfernen(h)
                entfernt += 1
        teile = []
        if geplant:
            teile.append(f"{geplant} Haushalt{'e' if geplant != 1 else ''} verlegt ab "
                         f"{ab:%d.%m.%Y}")  # fmt: skip
        if entfernt:
            teile.append(f"{entfernt} Plan{'ung' if entfernt == 1 else 'ungen'} zurückgenommen")
        messages.success(request, (", ".join(teile) + ".") if teile else "Nichts geändert.")
        return redirect("kunden:ausgabestelle", pk=stelle.pk)
    # Umzug ab dem Tag NACH dem letzten Ausgabetag (schliesst_am ist der letzte Tag selbst).
    vorgabe = (
        stelle.schliesst_am + dt.timedelta(days=1) if stelle.schliesst_am else timezone.localdate()
    )
    zeilen = [
        {"h": h, "hauptperson": next((p for p in h.personen.all() if p.ist_hauptperson), None),
         "offen": offen.get(h.pk)}
        for h in haushalte
    ]  # fmt: skip
    return render(request, "kunden/ausgabestelle_verlegen.html", {
        "s": stelle, "zeilen": zeilen, "ziele": ziele, "vorgabe": vorgabe,
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
