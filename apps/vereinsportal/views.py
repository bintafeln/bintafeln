from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.konten import rollen
from apps.konten.views import nicht_in_demo
from apps.spenden.models import Spende
from apps.vereinsportal import abruf as portal
from apps.vereinsportal import einlesen
from apps.vereinsportal.forms import (
    AbrufForm,
    EinstellungenForm,
    FinanzexportForm,
    SpenderlisteForm,
)
from apps.vereinsportal.models import Kontakt, PortalEinstellungen

nutzen = rollen.recht_erforderlich("vereinsportal.nutzen")


def _finanzexport(request, datei) -> None:
    if datei.name.lower().endswith(".xlsx"):
        e = einlesen.uebersicht_einlesen(datei.read())
    else:
        e = einlesen.finanzexport_einlesen(datei, request.user.get_username())
    messages.success(request, einlesen.bericht(e))


def _spenderliste(request, datei) -> None:
    anzahl, ohne_mail = einlesen.spenderliste_einlesen(datei.read())
    messages.success(request, portal.spenderliste_bericht(anzahl, ohne_mail))


def stand_je_jahr() -> list[dict]:
    """Was aus dem Vereinsportal im Spendenpool liegt: je Jahr Anzahl, dort schon versendet und
    noch offen."""
    V = Spende.Fremdbeleg.VERSENDET
    zeilen = (Spende.objects.filter(fremdbeleg__in=einlesen.FREMD)
              .values("datum__year").order_by("-datum__year")
              .annotate(anzahl=Count("pk"), versendet=Count("pk", filter=Q(fremdbeleg=V)),
                        spender=Count("adresse", distinct=True)))  # fmt: skip
    return [{"jahr": z["datum__year"], "anzahl": z["anzahl"], "versendet": z["versendet"],
             "offen": z["anzahl"] - z["versendet"], "spender": z["spender"]}
            for z in zeilen]  # fmt: skip


@never_cache
@nutzen
def start(request):
    """Finanzexport und Spenderliste einlesen; die Spenden selbst stehen in der Spendenliste."""
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
        return redirect("vereinsportal:start")
    return render(request, "vereinsportal/start.html", {
        "jahre": stand_je_jahr(), "kontakte": Kontakt.objects.count(),
        "finanzexport": FinanzexportForm(), "spenderliste": SpenderlisteForm(),
        "abruf_verfuegbar": portal.verfuegbar(),
    })  # fmt: skip


@never_cache
@nutzen
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=PortalEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("vereinsportal:einstellungen")
    return render(request, "vereinsportal/einstellungen.html", {
        "form": form, "abruf_verfuegbar": portal.verfuegbar(),
        "passwort_gespeichert": bool(form.instance.passwort_verschluesselt),
    })  # fmt: skip


# --- Automatischer Abruf (ADR 0127) ------------------------------------------------------------


def _abruf_stand(request, s=None):
    s = s or portal.stand()
    return render(request, "vereinsportal/_abruf_stand.html", {"s": s, "aktiv": s["stand"]
                  in portal.AKTIV})  # fmt: skip


@never_cache
@nutzen
def abruf(request):
    """Abruf starten und seinen Stand zeigen."""
    if not portal.verfuegbar():
        return render(request, "vereinsportal/abruf.html", {"verfuegbar": False})
    heute = timezone.localdate()
    form = AbrufForm(request.POST or None, initial={"von": heute.replace(day=1), "bis": heute})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            _abruf_starten(request, d)
        except portal.AbrufFehler as fehler:
            messages.error(request, str(fehler))
        return redirect("vereinsportal:abruf")
    return render(request, "vereinsportal/abruf.html", {
        "verfuegbar": True, "form": form, "s": portal.stand(),
        "eingerichtet": PortalEinstellungen.laden().abruf_eingerichtet,
    })  # fmt: skip


@nicht_in_demo
def _abruf_starten(request, d):
    portal.starten(d["von"], d["bis"], d["mit_liste"])


@never_cache
@nutzen
def abruf_stand(request):
    """Der Stand zum Nachladen; POST reicht den 2FA-Code weiter, bricht ab oder liest ein."""
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        try:
            if aktion == "code":
                portal.code_senden(request.POST.get("code") or "")
            elif aktion == "abbrechen":
                portal.abbrechen()
            elif aktion == "verwerfen":
                portal.verwerfen()
            elif aktion == "einlesen":
                for gelungen, text in portal.uebernehmen(request.user.get_username()):
                    (messages.success if gelungen else messages.error)(request, text)
        except portal.AbrufFehler as fehler:
            messages.error(request, str(fehler))
    return _abruf_stand(request)
