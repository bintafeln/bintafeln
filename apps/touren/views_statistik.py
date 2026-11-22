"""Statistik der Touren (ADR 0157): Kennzahlen und Abschnitte mit Grafik, Tabelle und CSV."""

import csv

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.konten import rollen
from apps.touren import statistik
from apps.touren.models import TourenEinstellungen


@never_cache
@rollen.recht_erforderlich("touren.statistik")
def uebersicht(request):
    heute = timezone.localdate()
    waehlbar = statistik.jahre(heute)
    wahl = request.GET.get("jahr", "")
    jahr = int(wahl) if wahl.isdigit() and int(wahl) in waehlbar else heute.year
    daten = statistik.Daten(jahr)
    teile = statistik.abschnitte(daten)
    teil = next((t for t in teile if t["id"] == request.GET.get("csv")), None)
    if teil is not None:
        antwort = HttpResponse(content_type="text/csv; charset=utf-8")
        antwort["Content-Disposition"] = f'attachment; filename="touren-{teil["id"]}-{jahr}.csv"'
        antwort.write("﻿")
        schreiber = csv.writer(antwort, delimiter=";")
        schreiber.writerow(teil["kopf"])
        schreiber.writerows(teil["zeilen"])
        return antwort
    return render(request, "touren/statistik.html", {
        "jahr": jahr, "jahre": waehlbar, "abschnitte": teile, "abfrage": f"jahr={jahr}",
        "k": statistik.kennzahlen(daten), "kiste_kg": TourenEinstellungen.laden().kiste_kg,
    })  # fmt: skip
