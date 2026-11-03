"""Bexat-Import (ADR 0100): Export hochladen, in das Importformat umwandeln und in den normalen
Import mit Abgleich übergeben. Es wird nichts ohne Abgleich gespeichert."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.bexat import konvertieren
from apps.bexat.forms import EinstellungenForm
from apps.bexat.models import BexatEinstellungen
from apps.konten import rollen

MAX_DATEIGROESSE = 60 * 1024 * 1024  # 60 MB


def _csv_antwort(name: str, inhalt: bytes) -> HttpResponse:
    antwort = HttpResponse(inhalt, content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = f'attachment; filename="{name}"'
    return antwort


@rollen.recht_erforderlich("kunden.importieren")
def start(request):
    einstellungen = BexatEinstellungen.laden()
    if request.method != "POST":
        return render(request, "bexat/start.html", {"einstellungen": einstellungen})

    datei = request.FILES.get("datei")
    ziel = request.POST.get("ziel")
    if datei is None:
        messages.error(request, "Bitte zuerst die Bexat-Exportdatei (.xlsx) auswählen.")
        return render(request, "bexat/start.html", {"einstellungen": einstellungen})
    if datei.size > MAX_DATEIGROESSE:
        messages.error(request, "Die Datei darf höchstens 60 MB groß sein.")
        return render(request, "bexat/start.html", {"einstellungen": einstellungen})

    try:
        umw = konvertieren.umwandeln(
            datei.read(),
            einkommensarten=einstellungen.einkommensarten,
            ausgabestellen=einstellungen.ausgabestellen,
        )
    except konvertieren.BexatFehler as fehler:
        messages.error(request, str(fehler))
        return render(request, "bexat/start.html", {"einstellungen": einstellungen})

    for hinweis in umw.hinweise:
        messages.warning(request, hinweis)

    if ziel == "antraege":
        return _csv_antwort("antraege.csv", umw.antraege)
    if ziel == "mitarbeitende":
        return _csv_antwort("mitarbeitende.csv", umw.mitarbeitende)

    # Vorgabe: Kundenstamm. Dieselbe Prüfung wie beim Importformat, dann der bekannte Abgleich.
    from apps.kunden import importieren, merkmale
    from apps.kunden.models import ImportVorbereitung

    # Merkmale, die der Umwandler füllt (z. B. „Schwerbehindert"), anlegen/aktivieren – sonst
    # überspringt der Import die Spalte stillschweigend und die Angabe geht verloren.
    for name in merkmale.aktivieren(*konvertieren.GELIEFERTE_MERKMALE):
        messages.info(
            request,
            f"Das Merkmal „{name}“ wurde für den Import angelegt bzw. wieder eingeschaltet, "
            "damit die Angabe aus Bexat nicht verloren geht.",
        )
    ergebnis = importieren.pruefen(umw.kundenstamm)
    if ergebnis.daten is None:
        return render(
            request,
            "bexat/start.html",
            {
                "einstellungen": einstellungen,
                "bericht": importieren.bericht_gruppiert(ergebnis.bericht),
            },
        )
    vorbereitung = ImportVorbereitung.objects.create(
        erstellt_von=request.user,
        dateien=ergebnis.dateien,
        pruefsumme=ergebnis.pruefsumme,
        daten=ergebnis.daten,
        bericht=ergebnis.bericht,
    )
    return redirect("kunden:import_vorschau", pk=vorbereitung.pk)


@rollen.recht_erforderlich("kunden.importieren")
def einstellungen(request):
    objekt = BexatEinstellungen.laden()
    if request.method == "POST":
        form = EinstellungenForm(request.POST)
        if form.is_valid():
            objekt.ausgabestellen = form.cleaned_data["ausgabestellen"]
            objekt.einkommensarten = form.cleaned_data["einkommensarten"]
            objekt.save()
            messages.success(request, "Gespeichert.")
            return redirect(reverse("bexat:einstellungen"))
    else:
        form = EinstellungenForm.aus_einstellungen(objekt)
    return render(request, "bexat/einstellungen.html", {"form": form})
