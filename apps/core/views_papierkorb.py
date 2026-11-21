"""Papierkorb: gelöschte Daten ansehen, wiederherstellen, endgültig löschen (ADR 0073)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import papierkorb
from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Zugriff


def _eintrag(request, pk):
    eintrag = papierkorb.sichtbar(request.user).filter(pk=pk).first()
    if eintrag is None:
        raise Http404
    return eintrag


@never_cache
@login_required
def liste(request):
    eintraege = papierkorb.sichtbar(request.user)
    arten = sorted(set(eintraege.values_list("art", flat=True)))
    art = request.GET.get("art", "")
    if art:
        eintraege = eintraege.filter(art=art)
    tage = TafelEinstellungen.laden().papierkorb_tage
    eintraege = list(eintraege.defer("daten", "verweise"))
    for e in eintraege:
        e.endgueltig_am = papierkorb.endgueltig_am(e, tage)
    return render(request, "core/papierkorb.html",
                  {"eintraege": eintraege, "arten": arten, "art": art, "tage": tage})  # fmt: skip


@never_cache
@login_required
def ansehen(request, pk):
    eintrag = _eintrag(request, pk)
    tage = TafelEinstellungen.laden().papierkorb_tage
    eintrag.endgueltig_am = papierkorb.endgueltig_am(eintrag, tage)
    # Kundendaten können Angaben der besonderen Kategorie (Art. 9) enthalten: Inhalte nur mit
    # diesem Recht, und jeder Abruf steht im Zugriffsprotokoll wie bei der Seite des Haushalts
    art9 = rollen.hat_recht(request.user, "kunden.besondere_kategorie")
    details = not eintrag.kundennummer or art9
    if eintrag.kundennummer and details:
        Zugriff.objects.create(benutzer=request.user, benutzername=request.user.get_username(),
                               kundennummer=eintrag.kundennummer,
                               besondere_kategorie=True)  # fmt: skip
    return render(request, "core/papierkorb_eintrag.html", {
        "eintrag": eintrag, "inhalt": papierkorb.inhalt(eintrag), "details": details,
    })  # fmt: skip


@require_POST
@login_required
def wiederherstellen(request, pk):
    eintrag = _eintrag(request, pk)
    try:
        papierkorb.wiederherstellen(eintrag, request.user)
    except papierkorb.PapierkorbFehler as fehler:
        messages.error(request, str(fehler))
        return redirect("core:papierkorb_eintrag", pk=pk)
    messages.success(request, f"{eintrag.art} „{eintrag.bezeichnung}“ wiederhergestellt.")
    return redirect("core:papierkorb")


@require_POST
@login_required
def endgueltig_loeschen(request, pk):
    eintrag = _eintrag(request, pk)
    papierkorb.endgueltig_loeschen(eintrag)
    messages.success(request, f"{eintrag.art} „{eintrag.bezeichnung}“ endgültig gelöscht.")
    return redirect("core:papierkorb")
