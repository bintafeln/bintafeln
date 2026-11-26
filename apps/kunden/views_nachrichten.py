"""Nachrichten der Ausgabestellen an die Verwaltung zu Kunden, die sie nicht aufrufen dürfen
(ADR 0062). Wer schreibt, sieht keine Daten des Kunden; die Verwaltung liest und erledigt."""

from collections import Counter

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core.auswahl import NACHRICHT_ANLIEGEN, NACHRICHT_ANLIEGEN_WAEHLBAR
from apps.konten import rollen
from apps.kunden import an_stelle, an_verwaltung
from apps.kunden.models import Ausweisdruck, Haushalt, Nachricht, StellenNachricht


def _stelle(request):
    """Ausgabestelle aus dem Auswahlfeld im Menü bzw. die des Kontos (ADR 0067)."""
    from apps.ausgabe.stelle import aktuelle

    return aktuelle(request.user)


@require_POST
@rollen.recht_erforderlich("einlass.nutzen", "kunden.liste")
def schreiben(request, kundennummer):
    get_object_or_404(Haushalt, kundennummer=kundennummer)  # zeigt nichts vom Kunden
    text = request.POST.get("text", "").strip()[:1000]
    anliegen = request.POST.get("anliegen", "sonstiges")
    if anliegen not in dict(NACHRICHT_ANLIEGEN_WAEHLBAR):
        anliegen = "sonstiges"
    zurueck = request.POST.get("zurueck", "")
    if not url_has_allowed_host_and_scheme(zurueck, allowed_hosts={request.get_host()}):
        zurueck = "/"
    if not text and anliegen == "sonstiges":
        messages.error(request, "Bitte eine Nachricht eingeben oder ein Anliegen wählen.")
        return redirect(zurueck)
    von = request.user.get_full_name() or request.user.get_username()
    Nachricht.objects.create(kundennummer=kundennummer, anliegen=anliegen, text=text,
                             stelle=_stelle(request), von=von)  # fmt: skip
    messages.success(request, f"Nachricht zu Kunde {kundennummer} an die Verwaltung gesendet.")
    return redirect(zurueck)


class VerwaltungForm(forms.Form):
    betreff = forms.CharField(label="Betreff", max_length=200)
    text = forms.CharField(label="Nachricht", max_length=2000,
                           widget=forms.Textarea(attrs={"rows": 6}))  # fmt: skip


ALLGEMEIN = "allgemein"  # Reiter für Nachrichten ohne Kunden (ADR 0140)


def offene() -> int:
    zu_kunden = Nachricht.objects.filter(erledigt_am__isnull=True).count()
    return zu_kunden + an_verwaltung.offene_anzahl()


def offene_je_anliegen() -> list[tuple[str, str, int]]:
    """(Schlüssel, Bezeichnung, Anzahl) der offenen Nachrichten, für die Startseite."""
    zahlen = Counter(Nachricht.objects.filter(erledigt_am__isnull=True)
                     .values_list("anliegen", flat=True))  # fmt: skip
    allgemein = an_verwaltung.offene_anzahl()
    return ([(ALLGEMEIN, "ohne Kunde", allgemein)] if allgemein else []) + [
        (k, name, zahlen[k]) for k, name in NACHRICHT_ANLIEGEN if zahlen[k]
    ]


@never_cache
@rollen.recht_erforderlich("einlass.nutzen")
def an_die_verwaltung(request):
    """Ausgabestelle schreibt an die Verwaltung (ohne Kunden) und sieht ihre letzten Nachrichten
    mit den Antworten (ADR 0140)."""
    stelle = _stelle(request)
    form = VerwaltungForm(request.POST if request.method == "POST" else None)
    if stelle is not None and form.is_valid():
        basis = request.build_absolute_uri("/").rstrip("/")
        an_verwaltung.schreiben(stelle, request.user, form.cleaned_data["betreff"],
                                form.cleaned_data["text"], basis=basis)  # fmt: skip
        messages.success(request, "Nachricht an die Verwaltung gesendet. Die Antwort "
                         "erscheint hier und auf der Startseite.")  # fmt: skip
        return redirect("kunden:an_verwaltung")
    return render(request, "kunden/an_verwaltung.html", {
        "stelle": stelle, "form": form, "nachrichten": an_verwaltung.von_stelle(stelle),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("einlass.nutzen")
def antwort_gelesen(request, pk):
    n = get_object_or_404(an_verwaltung.antworten_offen(_stelle(request)), pk=pk)
    an_verwaltung.gelesen(n, request.user)
    zurueck = request.POST.get("zurueck", "")
    if not url_has_allowed_host_and_scheme(zurueck, allowed_hosts={request.get_host()}):
        zurueck = "/"
    return redirect(zurueck)


@never_cache
@rollen.recht_erforderlich("kunden.nachrichten")
def liste(request):
    if request.method == "POST" and "stellen_nachricht" in request.POST:
        pk = request.POST["stellen_nachricht"]
        n = get_object_or_404(StellenNachricht, pk=int(pk) if pk.isdigit() else 0)
        if antwort := request.POST.get("antwort", "").strip():
            an_verwaltung.antworten(n, antwort, request.user)
            messages.success(request, "Antwort an " + (n.stelle.name if n.stelle else
                             "die Ausgabestelle") + " gesendet, Nachricht erledigt.")  # fmt: skip
        else:
            an_verwaltung.umschalten(n, request.user)
        return redirect(f"{reverse('kunden:nachrichten')}?anliegen={ALLGEMEIN}")
    if request.method == "POST":
        n = get_object_or_404(Nachricht, pk=request.POST.get("nachricht") or 0)
        if antwort := request.POST.get("antwort", "").strip():
            an_stelle.antworten(n, antwort, request.user)
            messages.success(request, "Antwort an " + (n.stelle.name if n.stelle else
                             "die Ausgabestelle") + " gesendet, Nachricht erledigt.")  # fmt: skip
        elif n.erledigt_am:
            n.erledigt_am, n.erledigt_von = None, ""
        else:
            n.erledigt_am, n.erledigt_von = timezone.now(), request.user.get_username()
        n.save()
        weiter = request.POST.get("weiter", "")
        if not url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}):
            weiter = "kunden:nachrichten"
        return redirect(weiter)
    alle = Nachricht.objects.select_related("stelle")
    anliegen = request.GET.get("anliegen", "")
    zahlen = Counter(Nachricht.objects.filter(erledigt_am__isnull=True)
                     .values_list("anliegen", flat=True))  # fmt: skip
    # nur Anliegen mit offenen Nachrichten als Reiter (und das gewählte), mit Zahl
    reiter = [(k, name, zahlen[k]) for k, name in NACHRICHT_ANLIEGEN_WAEHLBAR
              if zahlen[k] or k == anliegen]  # fmt: skip
    allgemein = StellenNachricht.objects.select_related("stelle")
    allgemein_offen = list(allgemein.filter(erledigt_am__isnull=True))
    if allgemein_offen or anliegen == ALLGEMEIN:
        reiter.insert(0, (ALLGEMEIN, "ohne Kunde", len(allgemein_offen)))
    if anliegen in dict(NACHRICHT_ANLIEGEN):
        alle = alle.filter(anliegen=anliegen)
    darf_drucken = rollen.hat_recht(request.user, "kunden.ausweis")
    gemeldet = besondere = 0
    if darf_drucken:
        haushalte, mit_rollstuhl = an_stelle.gemeldete()
        gemeldet, besondere = haushalte.count(), mit_rollstuhl.count()
    return render(request, "kunden/nachrichten.html", {
        "offen": alle.filter(erledigt_am__isnull=True),
        "erledigt": list(alle.filter(erledigt_am__isnull=False).order_by("-erledigt_am")[:100]),
        "offen_gesamt": sum(zahlen.values()) + len(allgemein_offen),
        "allgemein": ALLGEMEIN, "allgemein_offen": allgemein_offen,
        "allgemein_erledigt": list(allgemein.filter(erledigt_am__isnull=False)
                                   .order_by("-erledigt_am")[:100]),
        "tage": Nachricht.AUFBEWAHREN_TAGE,
        "anliegen": anliegen, "anliegen_liste": reiter,
        "darf_verlaengern": rollen.hat_recht(request.user, "kunden.bearbeiten"),
        "ausweisdrucke": list(an_stelle.letzte_drucke()) if darf_drucken else [],
        "zurueck_tage": an_stelle.ZURUECK_TAGE,
        "ausweise_gemeldet": gemeldet, "ausweise_besondere": besondere,
        "ausweise_uebrige": gemeldet - besondere,
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("kunden.ausweis")
def ausweisdruck(request, pk, was):
    """Nach „Alle gemeldeten Ausweise drucken“: bestätigen, dass alles gedruckt ist, oder den
    ganzen Druck zurücknehmen (ADR 0167)."""
    druck = get_object_or_404(Ausweisdruck, pk=pk)
    try:
        if was == "bestaetigen":
            an_stelle.druck_bestaetigen(druck, request.user)
            messages.success(request, "Der Druck ist ausgeblendet.")
        elif was == "zuruecknehmen":
            anzahl = an_stelle.druck_zuruecknehmen(druck, request.user)
            messages.success(request, f"Der Druck ist zurückgenommen: {anzahl} "
                             f"Meldung{'en' if anzahl != 1 else ''} wieder offen. „Alle "
                             "gemeldeten Ausweise drucken“ druckt sie erneut.")  # fmt: skip
        else:
            raise Http404
    except an_stelle.DruckFehler as fehler:
        messages.error(request, str(fehler))
    return redirect("kunden:nachrichten")
