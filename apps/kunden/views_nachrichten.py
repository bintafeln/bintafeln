"""Nachrichten der Ausgabestellen an die Verwaltung zu Kunden, die sie nicht aufrufen dürfen
(ADR 0062). Wer schreibt, sieht keine Daten des Kunden; die Verwaltung liest und erledigt."""

from collections import Counter

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core.auswahl import NACHRICHT_ANLIEGEN
from apps.konten import rollen
from apps.kunden.models import Haushalt, Nachricht


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
    if anliegen not in dict(NACHRICHT_ANLIEGEN):
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


def offene() -> int:
    return Nachricht.objects.filter(erledigt_am__isnull=True).count()


def offene_je_anliegen() -> list[tuple[str, str, int]]:
    """(Schlüssel, Bezeichnung, Anzahl) der offenen Nachrichten, für die Startseite."""
    zahlen = Counter(Nachricht.objects.filter(erledigt_am__isnull=True)
                     .values_list("anliegen", flat=True))  # fmt: skip
    return [(k, name, zahlen[k]) for k, name in NACHRICHT_ANLIEGEN if zahlen[k]]


@never_cache
@rollen.recht_erforderlich("kunden.nachrichten")
def liste(request):
    if request.method == "POST":
        n = get_object_or_404(Nachricht, pk=request.POST.get("nachricht") or 0)
        if n.erledigt_am:
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
    if anliegen in dict(NACHRICHT_ANLIEGEN):
        alle = alle.filter(anliegen=anliegen)
    return render(request, "kunden/nachrichten.html", {
        "offen": alle.filter(erledigt_am__isnull=True),
        "erledigt": alle.filter(erledigt_am__isnull=False).order_by("-erledigt_am")[:100],
        "tage": Nachricht.AUFBEWAHREN_TAGE,
        "anliegen": anliegen, "anliegen_liste": NACHRICHT_ANLIEGEN,
        "darf_verlaengern": rollen.hat_recht(request.user, "kunden.bearbeiten"),
    })  # fmt: skip
