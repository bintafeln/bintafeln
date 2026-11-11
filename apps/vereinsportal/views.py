from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from apps.core import listenexport, privatdateien
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.vereinsportal import auswertung, einlesen
from apps.vereinsportal.forms import EinstellungenForm, FinanzexportForm, SpenderlisteForm
from apps.vereinsportal.models import Beleg, Kontakt, PortalEinstellungen

nutzen = rollen.recht_erforderlich("vereinsportal.nutzen")
GRUPPEN = dict(auswertung.GRUPPEN)


def _jahr(request) -> int:
    jahre = auswertung.jahre()
    wahl = request.GET.get("jahr") or request.POST.get("jahr") or ""
    return int(wahl) if wahl.isdigit() and int(wahl) in jahre else jahre[0]


def _finanzexport(request, datei) -> None:
    if datei.name.lower().endswith(".xlsx"):
        e = einlesen.uebersicht_einlesen(datei.read())
    else:
        e = einlesen.finanzexport_einlesen(datei, request.user.get_username())
    teile = [f"{e.neu} neue Belege eingelesen", f"{e.doppelt} waren schon vorhanden"]
    if e.ohne_anschrift:
        teile.append(f"{e.ohne_anschrift} ohne vollständige Anschrift ausgelassen")
    teile.append(
        f"{e.versendet} als im Vereinsportal versendet vermerkt" if e.mit_uebersicht
        else "keine Übersicht der versendeten Belege in der Datei gefunden"
    )  # fmt: skip
    messages.success(request, ", ".join(teile) + ".")


def _spenderliste(request, datei) -> None:
    anzahl, ohne_mail = einlesen.spenderliste_einlesen(datei.read())
    zusatz = f" {ohne_mail} Zeilen ohne gültige E-Mail ausgelassen." if ohne_mail else ""
    messages.success(request, f"Liste ersetzt: {anzahl} Spender mit E-Mail.{zusatz}")


@never_cache
@nutzen
def start(request):
    """Einlesen und die Spender des Jahres nach Gruppen."""
    jahr = _jahr(request)
    if request.method == "POST":
        formulare = {"finanzexport": (FinanzexportForm, _finanzexport),
                     "spenderliste": (SpenderlisteForm, _spenderliste)}  # fmt: skip
        feld = "spenderliste" if "spenderliste" in request.FILES else "finanzexport"
        klasse, einlesen_mit = formulare[feld]
        form = klasse(request.POST, request.FILES)
        if form.is_valid():
            try:
                einlesen_mit(request, form.cleaned_data[feld])
            except einlesen.EinleseFehler as fehler:
                messages.error(request, str(fehler))
        else:
            messages.error(request, "Bitte eine Datei wählen.")
        return redirect(f"{reverse('vereinsportal:start')}?jahr={jahr}")
    alle = auswertung.spender(jahr)
    gruppe = request.GET.get("gruppe") if request.GET.get("gruppe") in GRUPPEN else ""
    return render(request, "vereinsportal/start.html", {
        "jahr": jahr, "jahre": auswertung.jahre(), "gruppe": gruppe,
        "zahlen": auswertung.zahlen(alle),
        "spender": [s for s in alle if not gruppe or s.gruppe == gruppe],
        "belege": Beleg.objects.filter(jahr=jahr).count(),
        "kontakte": Kontakt.objects.count(),
        "finanzexport": FinanzexportForm(), "spenderliste": SpenderlisteForm(),
        "gruppen": auswertung.GRUPPEN,
    })  # fmt: skip


@never_cache
@nutzen
def export(request):
    jahr = _jahr(request)
    gruppe = request.GET.get("gruppe") if request.GET.get("gruppe") in GRUPPEN else ""
    liste = [s for s in auswertung.spender(jahr) if not gruppe or s.gruppe == gruppe]
    titel = f"{GRUPPEN.get(gruppe, 'Spender aus dem Vereinsportal')} {jahr}"
    return listenexport.ausliefern(
        request,
        titel,
        f"spender-{gruppe or 'alle'}-{jahr}",
        auswertung.csv_text(liste),
        weiter=f"{reverse('vereinsportal:start')}?jahr={jahr}",
    )


@never_cache
@nutzen
def beleg(request, pk):
    b = get_object_or_404(Beleg, pk=pk)
    inhalt = privatdateien.lesen(Beleg.ORDNER, b.datei)
    if inhalt is None:
        raise Http404("Datei nicht mehr lesbar.")
    return pdf_antwort(inhalt, b.dateiname)


@never_cache
@nutzen
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=PortalEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("vereinsportal:einstellungen")
    return render(request, "vereinsportal/einstellungen.html", {"form": form})
