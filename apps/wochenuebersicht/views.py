import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle
from apps.wochenuebersicht import auswertung, pdf
from apps.wochenuebersicht.forms import SelbstabholerForm
from apps.wochenuebersicht.models import Selbstabholer, StellenReihenfolge

sehen = rollen.recht_erforderlich("wochenuebersicht.sehen")
bearbeiten = rollen.recht_erforderlich("wochenuebersicht.bearbeiten")


def _woche(request) -> dt.date | None:
    """Montag der gewählten Kalenderwoche (Feld ``kw`` im Format JJJJ-Www) oder None."""
    if not request.GET.get("abholungen"):
        return None
    try:
        return dt.datetime.strptime(request.GET.get("kw", "") + "-1", "%G-W%V-%u").date()
    except ValueError:
        return auswertung.montag(timezone.localdate())


@never_cache
@sehen
def uebersicht(request):
    heute = timezone.localdate()
    woche = _woche(request)
    daten = auswertung.uebersicht(heute, woche)
    kw = (woche or auswertung.montag(heute)).strftime("%G-W%V")
    return render(request, "wochenuebersicht/uebersicht.html", {**daten, "kw": kw,
                  "abfrage": request.GET.urlencode()})  # fmt: skip


@never_cache
@sehen
def als_pdf(request, art):
    daten = auswertung.uebersicht(timezone.localdate(), _woche(request))
    inhalt = pdf.querformat(daten) if art == "quer" else pdf.hochformat(daten)
    return pdf_antwort(inhalt, f"wochenuebersicht-{art}-{timezone.localdate():%Y-%m-%d}.pdf")


@never_cache
@bearbeiten
def selbstabholer(request):
    return render(request, "wochenuebersicht/selbstabholer.html",
                  {"liste": Selbstabholer.objects.all()})  # fmt: skip


@never_cache
@bearbeiten
def selbstabholer_bearbeiten(request, pk=None):
    s = get_object_or_404(Selbstabholer, pk=pk) if pk else Selbstabholer()
    form = SelbstabholerForm(request.POST or None, instance=s)
    if request.method == "POST" and form.is_valid():
        s = form.save()
        messages.success(request, f"„{s.name}“ gespeichert.")
        return redirect("wochenuebersicht:selbstabholer")
    return render(request, "wochenuebersicht/selbstabholer_bearbeiten.html",
                  {"form": form, "s": s if pk else None})  # fmt: skip


@require_POST
@bearbeiten
def selbstabholer_loeschen(request, pk):
    s = get_object_or_404(Selbstabholer, pk=pk)
    s.delete()
    messages.success(request, f"„{s.name}“ gelöscht.")
    return redirect("wochenuebersicht:selbstabholer")


@never_cache
@bearbeiten
def reihenfolge(request):
    stellen = list(Ausgabestelle.objects.order_by("name"))
    werte = dict(StellenReihenfolge.objects.values_list("ausgabestelle_id", "reihenfolge"))
    if request.method == "POST":
        for stelle in stellen:
            text = request.POST.get(f"r_{stelle.pk}", "").strip()
            if text.isdigit():
                StellenReihenfolge.objects.update_or_create(
                    ausgabestelle=stelle, defaults={"reihenfolge": min(int(text), 9999)}
                )
        messages.success(request, "Reihenfolge gespeichert.")
        return redirect("wochenuebersicht:reihenfolge")
    zeilen = sorted(((werte.get(s.pk, 100), s) for s in stellen), key=lambda x: (x[0], x[1].name))
    return render(request, "wochenuebersicht/reihenfolge.html", {"zeilen": zeilen})
