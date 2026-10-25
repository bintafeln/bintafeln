"""Sonderaktionen verwalten (Admin, Büro). Eingetragen wird am Einlass (views.py)."""

import csv

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.ausgabe.forms import SonderaktionForm
from apps.ausgabe.models import Sonderaktion
from apps.konten import rollen

buero = rollen.recht_erforderlich("sonderaktionen.verwalten")


@buero
def liste(request):
    heute = timezone.localdate()
    aktionen = Sonderaktion.objects.annotate(
        anzahl=Count("teilnahmen"), summe=Sum("teilnahmen__menge")
    )
    return render(
        request,
        "ausgabe/sonderaktionen.html",
        {
            "abschnitte": [
                ("Laufend", [a for a in aktionen if a.laeuft(heute)]),
                ("Geplant", [a for a in aktionen if a.von > heute]),
                ("Vorbei", [a for a in aktionen if a.bis < heute]),
            ]
        },
    )


@buero
def bearbeiten(request, pk=None):
    aktion = get_object_or_404(Sonderaktion, pk=pk) if pk else Sonderaktion()
    form = SonderaktionForm(request.POST or None, instance=aktion)
    if request.method == "POST" and form.is_valid():
        aktion = form.save()
        messages.success(request, f"Sonderaktion „{aktion}“ gespeichert.")
        return redirect("ausgabe:sonderaktion", pk=aktion.pk)
    return render(
        request,
        "ausgabe/sonderaktion_bearbeiten.html",
        {"form": form, "aktion": aktion if pk else None},
    )


@never_cache
@buero
def ansehen(request, pk):
    aktion = get_object_or_404(Sonderaktion, pk=pk)
    teilnahmen = aktion.teilnahmen.select_related("auswahl", "ausgabestelle")
    if request.GET.get("format") == "csv":
        return _csv(aktion, teilnahmen)
    je_auswahl = aktion.auswahl.annotate(anzahl=Count("teilnahmen"), summe=Sum("teilnahmen__menge"))
    ohne = teilnahmen.filter(auswahl__isnull=True).aggregate(anzahl=Count("pk"), summe=Sum("menge"))
    return render(
        request,
        "ausgabe/sonderaktion.html",
        {
            "aktion": aktion,
            "teilnahmen": teilnahmen,
            "je_auswahl": je_auswahl,
            "ohne": ohne,
            "gesamt": teilnahmen.aggregate(anzahl=Count("pk"), summe=Sum("menge")),
        },
    )


def _csv(aktion, teilnahmen):
    antwort = HttpResponse(content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = f'attachment; filename="sonderaktion-{aktion.pk}.csv"'
    antwort.write("﻿")  # damit Tabellenprogramme Umlaute richtig lesen
    schreiber = csv.writer(antwort, delimiter=";")
    schreiber.writerow(["kundennummer", "auswahl", "menge", "datum", "ausgabestelle", "von"])
    for t in teilnahmen:
        schreiber.writerow([
            t.kundennummer, t.auswahl.bezeichnung if t.auswahl else "", t.menge,
            f"{timezone.localtime(t.zeitpunkt):%d.%m.%Y %H:%M}",
            t.ausgabestelle.name if t.ausgabestelle else "", t.eingetragen_von,
        ])  # fmt: skip
    return antwort


@require_POST
@buero
def loeschen(request, pk):
    aktion = get_object_or_404(Sonderaktion, pk=pk)
    anzahl = aktion.teilnahmen.count()
    aktion.delete()
    messages.success(request, f"Sonderaktion „{aktion}“ mit {anzahl} Teilnahme(n) gelöscht.")
    return redirect("ausgabe:sonderaktionen")
