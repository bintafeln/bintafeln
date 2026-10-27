import datetime as dt

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import papierkorb
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle
from apps.wochenuebersicht import auswertung, pdf
from apps.wochenuebersicht.forms import KontakteFormset, NotizForm, SelbstabholerForm
from apps.wochenuebersicht.models import Selbstabholer, SelbstabholerNotiz, StellenReihenfolge

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
                  {"liste": Selbstabholer.objects.prefetch_related("kontakte")})  # fmt: skip


@never_cache
@bearbeiten
def selbstabholer_bearbeiten(request, pk=None):
    s = get_object_or_404(Selbstabholer, pk=pk) if pk else Selbstabholer()
    daten = request.POST if request.method == "POST" else None
    form = SelbstabholerForm(daten, instance=s)
    kontakte = KontakteFormset(daten, instance=s, prefix="k")
    if request.method == "POST" and form.is_valid() and kontakte.is_valid():
        with transaction.atomic():
            s = form.save()
            kontakte.instance = s
            kontakte.save()
        messages.success(request, f"„{s.name}“ gespeichert.")
        return redirect("wochenuebersicht:selbstabholer_bearbeiten", pk=s.pk)
    return render(request, "wochenuebersicht/selbstabholer_bearbeiten.html", {
        "form": form, "kontakte": kontakte, "s": s if pk else None,
        "notizen": s.notizen.all() if pk else [], "notiz_form": NotizForm(),
    })  # fmt: skip


@require_POST
@bearbeiten
def selbstabholer_notiz(request, pk):
    """Gesprächsnotiz anlegen (mit Datum und Verfasser)."""
    s = get_object_or_404(Selbstabholer, pk=pk)
    form = NotizForm(request.POST)
    if form.is_valid() and form.cleaned_data["text"].strip():
        notiz = form.save(commit=False)
        notiz.selbstabholer = s
        notiz.verfasst_von = (request.user.get_full_name() or request.user.get_username())[:150]
        notiz.save()
        messages.success(request, "Notiz gespeichert.")
    return redirect(f"{reverse('wochenuebersicht:selbstabholer_bearbeiten', args=[pk])}#notizen")


@require_POST
@bearbeiten
def selbstabholer_notiz_loeschen(request, pk):
    notiz = get_object_or_404(SelbstabholerNotiz, pk=pk)
    ziel = notiz.selbstabholer_id
    papierkorb.loeschen(request.user, "Notiz zu Selbstabholer",
                        f"{notiz.text[:60]} ({notiz.selbstabholer})", notiz,
                        recht="wochenuebersicht.bearbeiten")  # fmt: skip
    messages.success(request, "Notiz in den Papierkorb gelegt.")
    return redirect(f"{reverse('wochenuebersicht:selbstabholer_bearbeiten', args=[ziel])}#notizen")


@require_POST
@bearbeiten
def selbstabholer_loeschen(request, pk):
    s = get_object_or_404(Selbstabholer, pk=pk)
    papierkorb.loeschen(request.user, "Selbstabholer", s.name, s,
                        recht="wochenuebersicht.bearbeiten")  # fmt: skip
    messages.success(request, f"„{s.name}“ in den Papierkorb gelegt.")
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
