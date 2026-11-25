"""„Kunden herausnehmen“ auf der Kundenseite (ADR 0177). Regeln in ``herausnehmen.py``."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.konten import rollen
from apps.kunden import herausnehmen as regeln
from apps.kunden import zugang
from apps.kunden.models import Haushalt, Notiz

recht = rollen.recht_erforderlich("kunden.herausnehmen")


def _haushalt(request, kundennummer):
    return zugang.haushalt(request.user, kundennummer,
                           Haushalt.objects.prefetch_related("sperren", "personen"))  # fmt: skip


@never_cache
@recht
def herausnehmen(request, kundennummer):
    """Rückfrage mit allem, was man vorher wissen muss (letzter Besuch, Notizen – dort stehen
    Krankmeldungen), dann die Herausnahme."""
    h = _haushalt(request, kundennummer)
    heute = timezone.localdate()
    if request.method == "POST":
        try:
            sperre = regeln.herausnehmen(h, request.user, request.POST.get("begruendung", ""))
        except regeln.HerausnehmenFehler as grund:
            messages.error(request, str(grund))
        else:
            messages.success(request, f"Kunde {h.kundennummer} herausgenommen: Ausweis beendet, "
                             f"gesperrt bis {sperre.bis:%d.%m.%Y}.")  # fmt: skip
        return redirect("kunden:haushalt", h.kundennummer)
    return render(request, "kunden/herausnehmen.html", {
        "h": h, "faellig": regeln.faellig(h, heute), "bis": regeln.sperre_bis(heute),
        "begruendung": regeln.BEGRUENDUNG, "heute": heute,
        "notizen": Notiz.objects.filter(kundennummer=h.kundennummer)[:20],
    })  # fmt: skip


@require_POST
@recht
def zuruecknehmen(request, kundennummer):
    h = _haushalt(request, kundennummer)
    try:
        regeln.zuruecknehmen(h, request.user)
    except regeln.HerausnehmenFehler as grund:
        messages.error(request, str(grund))
    else:
        messages.success(request, "Herausnahme zurückgenommen: Die Sperre ist weg, der Ausweis "
                         "gilt wieder wie vorher. Bitte die Kundengruppe neu wählen.")  # fmt: skip
    return redirect("kunden:haushalt", h.kundennummer)
