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
    ZugangForm,
)
from apps.vereinsportal.models import Kontakt, PortalEinstellungen, Zugang

nutzen = rollen.recht_erforderlich("vereinsportal.nutzen")
abrufen = rollen.recht_erforderlich("vereinsportal.abruf")


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
    })  # fmt: skip


# --- Automatischer Abruf (ADR 0127, 0129) ------------------------------------------------------


def _abruf_stand(request, s=None):
    s = s or portal.stand()
    portal.abgleichen(s)
    laufender = portal.laufender()
    return render(request, "vereinsportal/_abruf_stand.html", {
        "s": s, "aktiv": s["stand"] in portal.AKTIV, "laufender": laufender,
        "meiner": bool(laufender and laufender.benutzer_id == request.user.pk),
        "historie": portal.historie(alle="alle" in request.GET),
    })  # fmt: skip


@never_cache
@abrufen
def abruf(request):
    """Abruf mit den eigenen Zugangsdaten starten; Stand und Historie sehen alle mit dem Recht."""
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
    s = portal.stand()
    portal.abgleichen(s)
    laufender = portal.laufender()
    return render(request, "vereinsportal/abruf.html", {
        "verfuegbar": True, "form": form, "s": s, "aktiv": s["stand"] in portal.AKTIV,
        "laufender": laufender,
        "meiner": bool(laufender and laufender.benutzer_id == request.user.pk),
        "adressen": PortalEinstellungen.laden().adressen_eingerichtet,
        "zugang": portal.zugang(request.user),
        "historie": portal.historie(alle="alle" in request.GET),
    })  # fmt: skip


@nicht_in_demo
def _abruf_starten(request, d):
    portal.starten(request.user, d["von"], d["bis"], d["mit_liste"])


@never_cache
@abrufen
def zugang(request):
    """Die eigenen Zugangsdaten zum Vereinsportal: Jedes Konto sieht und ändert nur seine."""
    eigener = Zugang.objects.filter(benutzer=request.user).first()
    if request.method == "POST" and "loeschen" in request.POST:
        _zugang_loeschen(request, eigener)
        return redirect("vereinsportal:abruf")
    form = ZugangForm(request.POST or None, instance=eigener or Zugang(benutzer=request.user))
    if request.method == "POST" and form.is_valid():
        _zugang_speichern(request, form)
        return redirect("vereinsportal:abruf")
    return render(request, "vereinsportal/zugang.html", {"form": form, "eigener": eigener})


@nicht_in_demo
def _zugang_speichern(request, form):
    form.save()
    messages.success(request, "Ihre Zugangsdaten sind gespeichert.")


@nicht_in_demo
def _zugang_loeschen(request, eigener):
    if eigener:
        eigener.delete()  # Geheimnis: endgültig, nicht in den Papierkorb
    messages.success(request, "Ihre Zugangsdaten sind gelöscht.")


@never_cache
@abrufen
def abruf_stand(request):
    """Der Stand zum Nachladen; POST reicht den 2FA-Code weiter, bricht ab oder liest ein."""
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        try:
            if aktion == "code":
                portal.code_senden(request.user, request.POST.get("code") or "")
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
