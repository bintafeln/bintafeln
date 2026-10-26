"""Speicher und Fotos (ADR 0064): Verkleinerung einstellen, Platz ansehen, Originale aufräumen."""

import datetime as dt

from django import forms
from django.contrib import messages
from django.db import connection
from django.shortcuts import redirect, render
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.core import privatdateien, sicherung
from apps.core.models import FotoEinstellungen
from apps.konten import rollen
from apps.konten.views import nicht_in_demo

SICHERUNG_HOECHSTENS = dt.timedelta(hours=24)  # vor dem Löschen der Originale


class FotoForm(forms.ModelForm):
    class Meta:
        model = FotoEinstellungen
        fields = ["kante", "qualitaet", "graustufen"]
        widgets = {"qualitaet": forms.NumberInput(attrs={"min": 40, "max": 95, "step": 5})}


def _datenbank_groesse() -> int | None:
    if connection.vendor != "postgresql":
        return None
    with connection.cursor() as c:
        c.execute("SELECT pg_database_size(current_database())")
        return c.fetchone()[0]


def _sicherung_frisch() -> bool:
    status = sicherung.lese_status()
    erfolgreich = status.letzte_erfolgreiche
    return erfolgreich is not None and timezone.now() - erfolgreich <= SICHERUNG_HOECHSTENS


@never_cache
@rollen.recht_erforderlich("einstellungen.tafel")
def seite(request):
    form = FotoForm(request.POST or None, instance=FotoEinstellungen.laden())
    aktion = request.POST.get("aktion")
    if request.method == "POST" and aktion == "speichern" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert. Neue Fotos werden ab jetzt so verkleinert.")
        return redirect("core:speicher")
    if request.method == "POST" and aktion == "verkleinern":
        e = privatdateien.vorhandene_verkleinern()
        text = (f"{e['verkleinert']} Foto(s) verkleinert, {filesizeformat(max(e['gespart'], 0))} "
                "gespart. Die Originale liegen noch daneben.")  # fmt: skip
        if e["offen"]:
            text += f" Noch {e['offen']} offen – bitte noch einmal auf „Verkleinern“ klicken."
        messages.success(request, text)
        return redirect("core:speicher")
    if request.method == "POST" and aktion == "originale":
        return _originale_loeschen(request)
    bestand = privatdateien.bestand()
    return render(request, "core/speicher.html", {
        "form": form, "bestand": bestand,
        "dateien": sum(z["bytes"] for z in bestand),
        "originale": sum(z["originale"] for z in bestand),
        "datenbank": _datenbank_groesse(),
        "sicherung_frisch": _sicherung_frisch(),
    })  # fmt: skip


@nicht_in_demo
def _originale_loeschen(request):
    if not _sicherung_frisch():
        messages.error(
            request,
            "Originale werden erst gelöscht, wenn eine Sicherung höchstens "
            "24 Stunden alt ist. Bitte zuerst eine Sicherung erstellen.",
        )
        return redirect("core:speicher")
    anzahl, frei = privatdateien.originale_loeschen()
    messages.success(request, f"{anzahl} Original(e) gelöscht, {filesizeformat(frei)} frei.")
    return redirect("core:speicher")
