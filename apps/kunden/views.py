import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core import sicherung
from apps.konten import rollen
from apps.kunden import importieren
from apps.kunden.forms import KundenEinstellungenForm, ZusatzfeldForm
from apps.kunden.models import (
    Abholer,
    Bemerkung,
    Haushalt,
    ImportLauf,
    ImportVorbereitung,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    Zusatzfeld,
)


@rollen.rolle_erforderlich(rollen.ADMIN)
def einstellungen(request):
    form = KundenEinstellungenForm(request.POST or None, instance=KundenEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen des Kundenstamms gespeichert.")
        return redirect("kunden:einstellungen")
    return render(
        request,
        "kunden/einstellungen.html",
        {"form": form, "zusatzfelder": Zusatzfeld.objects.all()},
    )


@rollen.rolle_erforderlich(rollen.ADMIN)
def zusatzfeld_bearbeiten(request, pk=None):
    feld = get_object_or_404(Zusatzfeld, pk=pk) if pk else Zusatzfeld()
    form = ZusatzfeldForm(request.POST or None, instance=feld)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Zusatzfeld „{feld.bezeichnung}“ gespeichert.")
        return redirect("kunden:einstellungen")
    return render(request, "kunden/zusatzfeld.html", {"form": form, "feld": feld})


# --- Übersicht und Import ---------------------------------------------------------------

MAX_DATEIGROESSE = 20 * 1024 * 1024
MAX_SICHERUNGSALTER = dt.timedelta(hours=24)


def _sicherung_frisch() -> bool:
    status = sicherung.lese_status()
    return (
        status.letzte_erfolgreiche is not None
        and timezone.now() - status.letzte_erfolgreiche <= MAX_SICHERUNGSALTER
    )


@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def uebersicht(request):
    ImportVorbereitung.abgelaufene_loeschen()
    return render(
        request,
        "kunden/uebersicht.html",
        {
            "anzahl": {
                "haushalte": Haushalt.objects.count(),
                "personen": Person.objects.count(),
                "kundengruppen": Kundengruppe.objects.count(),
            },
            "importe": ImportLauf.objects.select_related("benutzer")[:10],
        },
    )


@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_hochladen(request):
    ImportVorbereitung.abgelaufene_loeschen()
    kontext = {"sicherung_frisch": _sicherung_frisch()}
    if request.method == "POST":
        dateien = request.FILES.getlist("dateien")
        if not dateien:
            messages.error(request, "Bitte mindestens haushalte.csv auswählen.")
            return render(request, "kunden/import.html", kontext)
        zu_gross = [d.name for d in dateien if d.size > MAX_DATEIGROESSE]
        if zu_gross:
            messages.error(request, "Dateien dürfen höchstens 20 MB groß sein.")
            return render(request, "kunden/import.html", kontext)
        ergebnis = importieren.pruefen({d.name: d.read() for d in dateien})
        if ergebnis.daten is None:
            kontext["bericht"] = importieren.bericht_gruppiert(ergebnis.bericht)
            kontext["dateien"] = ergebnis.dateien
            return render(request, "kunden/import.html", kontext)
        vorbereitung = ImportVorbereitung.objects.create(
            erstellt_von=request.user,
            dateien=ergebnis.dateien,
            pruefsumme=ergebnis.pruefsumme,
            daten=ergebnis.daten,
            bericht=ergebnis.bericht,
        )
        return redirect("kunden:import_vorschau", pk=vorbereitung.pk)
    return render(request, "kunden/import.html", kontext)


def _vorbereitung_laden(request, pk):
    ImportVorbereitung.abgelaufene_loeschen()
    return ImportVorbereitung.objects.filter(pk=pk, erstellt_von=request.user).first()


@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_vorschau(request, pk):
    vorbereitung = _vorbereitung_laden(request, pk)
    if vorbereitung is None:
        messages.error(request, "Dieser Import ist abgelaufen oder existiert nicht mehr.")
        return redirect("kunden:import")
    daten = vorbereitung.daten
    return render(
        request,
        "kunden/import_vorschau.html",
        {
            "vorbereitung": vorbereitung,
            "bericht": importieren.bericht_gruppiert(vorbereitung.bericht),
            "anzahl_warnungen": len(vorbereitung.bericht),
            "neu": {
                "haushalte": len(daten["haushalte"]),
                "personen": len(daten["haushalte"]) + len(daten["personen"]),
                "abholer": len(daten["abholer"]),
                "sperren": len(daten["sperren"]),
                "bemerkungen": len(daten["bemerkungen"]),
            },
            "bisher": {
                "haushalte": Haushalt.objects.count(),
                "personen": Person.objects.count(),
                "abholer": Abholer.objects.count(),
                "sperren": Sperre.objects.count(),
                "bemerkungen": Bemerkung.objects.count(),
            },
            "gueltig_bis": vorbereitung.erstellt_am + ImportVorbereitung.GUELTIG,
            "sicherung_frisch": _sicherung_frisch(),
        },
    )


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_uebernehmen(request, pk):
    vorbereitung = _vorbereitung_laden(request, pk)
    if vorbereitung is None:
        messages.error(request, "Dieser Import ist abgelaufen oder existiert nicht mehr.")
        return redirect("kunden:import")
    if not _sicherung_frisch():
        messages.error(
            request,
            "Die letzte erfolgreiche Sicherung ist älter als 24 Stunden. Bitte zuerst auf dem "
            "Server „./betrieb sichern“ ausführen.",
        )
        return redirect("kunden:import_vorschau", pk=pk)
    lauf = importieren.uebernehmen(
        vorbereitung.daten,
        benutzer=request.user,
        dateien=vorbereitung.dateien,
        pruefsumme=vorbereitung.pruefsumme,
        anzahl_warnungen=len(vorbereitung.bericht),
    )
    vorbereitung.delete()
    messages.success(
        request,
        f"Import abgeschlossen: {lauf.anzahl_haushalte} Haushalte, "
        f"{lauf.anzahl_personen} Personen.",
    )
    return redirect("kunden:uebersicht")


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_verwerfen(request, pk):
    vorbereitung = _vorbereitung_laden(request, pk)
    if vorbereitung is not None:
        vorbereitung.delete()
    messages.info(request, "Import verworfen. Die geprüften Daten wurden gelöscht.")
    return redirect("kunden:import")
