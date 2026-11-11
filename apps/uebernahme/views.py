"""Übernahme aus einem anderen Programm (ADR 0100): Export hochladen, in das Importformat
umwandeln und in den normalen Import mit Abgleich übergeben. Es wird nichts ohne Abgleich
gespeichert."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.konten import rollen
from apps.uebernahme import besuche_konto as besuche_konto_
from apps.uebernahme import konvertieren
from apps.uebernahme.forms import EinstellungenForm
from apps.uebernahme.models import UebernahmeEinstellungen

MAX_DATEIGROESSE = 60 * 1024 * 1024  # 60 MB


def _csv_antwort(name: str, inhalt: bytes) -> HttpResponse:
    antwort = HttpResponse(inhalt, content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = f'attachment; filename="{name}"'
    return antwort


def _benutzername(user) -> str:
    return (user.get_full_name() or user.get_username())[:100]


@rollen.recht_erforderlich("kunden.importieren")
def start(request):
    einstellungen = UebernahmeEinstellungen.laden()
    if request.method != "POST":
        return render(request, "uebernahme/start.html", {"einstellungen": einstellungen})

    datei = request.FILES.get("datei")
    ziel = request.POST.get("ziel")
    if datei is None:
        messages.error(request, "Bitte zuerst die Exportdatei (.xlsx) auswählen.")
        return render(request, "uebernahme/start.html", {"einstellungen": einstellungen})
    if datei.size > MAX_DATEIGROESSE:
        messages.error(request, "Die Datei darf höchstens 60 MB groß sein.")
        return render(request, "uebernahme/start.html", {"einstellungen": einstellungen})

    if ziel == "besuche":
        # Tagesreport „kunden die da waren“ (ein Blatt, nur Nummern) → abholungen.csv zum
        # Herunterladen; anschließend über „Kundenstamm importieren → ergänzen“ einspielen.
        try:
            besuche = konvertieren.besuche_umwandeln(datei.read())
        except konvertieren.UebernahmeFehler as fehler:
            messages.error(request, str(fehler))
            return render(request, "uebernahme/start.html", {"einstellungen": einstellungen})
        return _csv_antwort("abholungen.csv", besuche.abholungen)

    try:
        umw = konvertieren.umwandeln(
            datei.read(),
            einkommensarten=einstellungen.einkommensarten,
            ausgabestellen=einstellungen.ausgabestellen,
        )
    except konvertieren.UebernahmeFehler as fehler:
        messages.error(request, str(fehler))
        return render(request, "uebernahme/start.html", {"einstellungen": einstellungen})

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
            "damit die Angabe aus dem bisherigen Programm nicht verloren geht.",
        )
    ergebnis = importieren.pruefen(umw.kundenstamm)
    if ergebnis.daten is None:
        return render(
            request,
            "uebernahme/start.html",
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
def besuche_konto(request):
    """Tagesliste der Abholungen aus dem bisherigen Programm übernehmen (ADR 0110): Besuche
    nachtragen und den Kontostand je Kunde per Korrektur-Buchung auf den Wert aus der Liste
    setzen. Erst Probelauf (bucht nichts), dann Übernehmen. Das Buchen braucht zusätzlich das
    Recht „Kundenkonto korrigieren“."""
    darf_buchen = rollen.hat_recht(request.user, "konto.korrektur")
    kontext = {"darf_buchen": darf_buchen}
    aktion = request.POST.get("aktion")
    if request.method == "POST":
        datei = request.FILES.get("datei")
        if datei is None:
            kontext["fehler"] = "Bitte zuerst die Tagesliste (CSV oder .xlsx) auswählen."
        elif datei.size > MAX_DATEIGROESSE:
            kontext["fehler"] = "Die Datei darf höchstens 60 MB groß sein."
        else:
            try:
                zeilen = besuche_konto_.lesen(datei.read())
            except besuche_konto_.BesucheFehler as fehler:
                kontext["fehler"] = str(fehler)
            else:
                if aktion == "uebernehmen":
                    if not darf_buchen:
                        messages.error(request, "Zum Buchen der Kontostände fehlt das Recht "
                                       "„Kundenkonto korrigieren“.")  # fmt: skip
                        return redirect("uebernahme:besuche_konto")
                    erg = besuche_konto_.uebernehmen(zeilen, _benutzername(request.user))
                    messages.success(
                        request,
                        f"{erg['besuche_neu']} Besuch(e) nachgetragen, "
                        f"{erg['korrekturen']} Kontostand/-stände korrigiert.",
                    )
                    if erg["unbekannt"]:
                        rest = " …" if len(erg["unbekannt"]) > 20 else ""
                        messages.warning(
                            request,
                            f"{len(erg['unbekannt'])} Kundennummer(n) gibt es in bintafeln nicht "
                            f"und wurden übersprungen: {', '.join(erg['unbekannt'][:20])}{rest}",
                        )
                    return redirect("uebernahme:besuche_konto")
                kontext["bericht"] = besuche_konto_.plan(zeilen)
    # Probelauf per htmx: nur den Bericht zurückgeben, damit die gewählte Datei oben stehen bleibt.
    if request.method == "POST" and aktion != "uebernehmen" and request.headers.get("HX-Request"):
        return render(request, "uebernahme/_besuche_konto_bericht.html", kontext)
    if "fehler" in kontext:
        messages.error(request, kontext["fehler"])
    return render(request, "uebernahme/besuche_konto.html", kontext)


@rollen.recht_erforderlich("kunden.importieren")
def einstellungen(request):
    objekt = UebernahmeEinstellungen.laden()
    if request.method == "POST":
        form = EinstellungenForm(request.POST)
        if form.is_valid():
            objekt.ausgabestellen = form.cleaned_data["ausgabestellen"]
            objekt.einkommensarten = form.cleaned_data["einkommensarten"]
            objekt.save()
            messages.success(request, "Gespeichert.")
            return redirect(reverse("uebernahme:einstellungen"))
    else:
        form = EinstellungenForm.aus_einstellungen(objekt)
    return render(request, "uebernahme/einstellungen.html", {"form": form})
