"""Arbeitszeit: eigene Zeiten stempeln, Korrekturen durch das Personal (ADR 0020)."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.ausgabe.konto import MONATE
from apps.core import papierkorb
from apps.konten import rollen
from apps.personal import arbeitszeit, berechnung
from apps.personal.forms import ArbeitszeitEinstellungenForm, ZeitbuchungForm
from apps.personal.models import ArbeitszeitEinstellungen, Zeitbuchung
from apps.personal.views import personal_erforderlich


def _monat(request) -> dt.date:
    try:
        return dt.datetime.strptime(request.GET.get("monat", ""), "%Y-%m").date()
    except ValueError:
        return timezone.localdate().replace(day=1)


def _verschieben(monat: dt.date, schritte: int) -> str:
    index = monat.year * 12 + monat.month - 1 + schritte
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _monatsdaten(person, monat: dt.date) -> dict:
    """Arbeitstage des Monats mit Pausen und Summe, dazu Blätter-Links."""
    zeitzone = timezone.get_current_timezone()
    anfang = dt.datetime.combine(monat, dt.time(), zeitzone)
    naechster = dt.date.fromisoformat(f"{_verschieben(monat, 1)}-01")
    ende = dt.datetime.combine(naechster, dt.time(), zeitzone)
    buchungen = person.zeitbuchungen.filter(beginn__gte=anfang, beginn__lt=ende)
    tage = berechnung.arbeitstage_aus(
        buchungen, ArbeitszeitEinstellungen.laden().pausen_automatisch
    )
    return {
        "monat": monat,
        "monat_titel": f"{MONATE[monat.month - 1]} {monat.year}",
        "frueher": _verschieben(monat, -1),
        "spaeter": _verschieben(monat, 1),
        "tage": tage,
        "summe": sum((t.netto for t in tage), berechnung.NULL),
    }


def _saldo(benutzer, heute):
    """Stand des Stundenkontos; None, wenn für die Person keines geführt wird."""
    konto = berechnung.stundenkonto(benutzer, heute.year, heute)
    return konto.saldo if konto.gefuehrt else None


@login_required
def meine(request):
    if not arbeitszeit.darf_stempeln(request.user):
        raise PermissionDenied
    heute = timezone.localdate()
    hat_vertrag = request.user.vertraege.exists()
    return render(
        request,
        "personal/meine_arbeitszeit.html",
        {
            "laufend": arbeitszeit.laufend(request.user),
            "in_pause": arbeitszeit.in_pause(request.user),
            "vergessen": arbeitszeit.vergessen(request.user),
            "stempeln_erlaubt": arbeitszeit.hier_erlaubt(request),
            "saldo": _saldo(request.user, heute) if hat_vertrag else None,
            **_monatsdaten(request.user, _monat(request)),
        },
    )


@require_POST
@login_required
def stempeln(request):
    if not arbeitszeit.darf_stempeln(request.user):
        raise PermissionDenied
    if not arbeitszeit.hier_erlaubt(request):
        messages.error(request, "Stempeln geht nur am Aushang-Monitor vor Ort: dort mit Name "
                       "und PIN, oder den QR-Code am Monitor mit dem Handy scannen.")  # fmt: skip
        return redirect("personal:meine_arbeitszeit")
    try:
        aktion = request.POST.get("aktion")
        aktion = aktion if aktion in ("pause", "gehen") else "kommen"
        messages.success(request, arbeitszeit.stempeln(request.user, aktion))
    except arbeitszeit.StempelFehler as fehler:
        messages.error(request, str(fehler))
    return redirect("personal:meine_arbeitszeit")


# --- Personal: Zeiten ansehen und korrigieren --------------------------------------------


@personal_erforderlich
def zeiten(request, pk):
    p = get_object_or_404(get_user_model(), pk=pk)
    return render(
        request,
        "personal/zeiten.html",
        {"p": p, "vergessen": arbeitszeit.vergessen(p), **_monatsdaten(p, _monat(request))},
    )


@personal_erforderlich
def zeit_bearbeiten(request, pk, buchung=None):
    p = get_object_or_404(get_user_model(), pk=pk)
    b = (
        get_object_or_404(Zeitbuchung, pk=buchung, benutzer=p)
        if buchung
        else Zeitbuchung(benutzer=p)
    )
    form = ZeitbuchungForm(request.POST or None, buchung=b)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            for buchung in (b, form.zweite):
                if buchung is not None:
                    buchung.korrigiert_von = request.user.get_username()
                    buchung.save()
        messages.success(request, "Zeitbuchung mit Pause gespeichert (zwei Zeiten)." if form.zweite
                         else "Zeitbuchung gespeichert.")  # fmt: skip
        beginn = timezone.localtime(b.beginn)
        return redirect(f"{reverse('personal:zeiten', args=[p.pk])}?monat={beginn:%Y-%m}")
    return render(request, "personal/zeitbuchung.html", {"p": p, "b": b, "form": form})


@require_POST
@personal_erforderlich
def zeit_loeschen(request, pk, buchung):
    b = get_object_or_404(Zeitbuchung, pk=buchung, benutzer_id=pk)
    monat = f"{timezone.localtime(b.beginn):%Y-%m}"
    papierkorb.loeschen(request.user, "Zeitbuchung", f"{b} ({b.benutzer})", b,
                        recht="personal.sehen")  # fmt: skip
    messages.success(request, "Zeitbuchung in den Papierkorb gelegt.")
    return redirect(f"{reverse('personal:zeiten', args=[pk])}?monat={monat}")


@rollen.recht_erforderlich("einstellungen.arbeitszeit")
def einstellungen(request):
    form = ArbeitszeitEinstellungenForm(
        request.POST or None, instance=ArbeitszeitEinstellungen.laden()
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen der Arbeitszeit gespeichert.")
        return redirect("personal:arbeitszeit_einstellungen")
    return render(request, "personal/arbeitszeit_einstellungen.html", {"form": form})
