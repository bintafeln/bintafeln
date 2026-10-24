"""Mitarbeitende verwalten: Liste, Archiv, anlegen, bearbeiten, sperren, zurücksetzen."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django_otp import user_has_device

from apps.core import mail
from apps.konten import einladung, rollen, verwaltung, zwei_faktor
from apps.konten.forms import MitarbeiterForm


def verwalter_erforderlich(ansicht):
    @wraps(ansicht)
    @login_required
    def pruefen(request, *args, **kwargs):
        if not rollen.darf_mitarbeitende_verwalten(request.user):
            raise PermissionDenied
        return ansicht(request, *args, **kwargs)

    return pruefen


def _zeilen(benutzer):
    """Konten mit Rollen (in fester Reihenfolge) und Zwei-Faktor-Stand für die Listen."""
    zeilen = []
    for b in benutzer.prefetch_related("groups").order_by("last_name", "first_name", "username"):
        namen = {g.name for g in b.groups.all()}
        zeilen.append(
            {
                "b": b,
                "rollen": [
                    r for r in rollen.ALLE if r in namen or (b.is_superuser and r == rollen.ADMIN)
                ],
                "zwei_faktor": user_has_device(b),
            }
        )
    return zeilen


@verwalter_erforderlich
def liste(request):
    return render(
        request,
        "konten/mitarbeitende.html",
        {"zeilen": _zeilen(get_user_model().objects.filter(is_active=True)), "archiv": False},
    )


@verwalter_erforderlich
def archiv(request):
    return render(
        request,
        "konten/mitarbeitende.html",
        {"zeilen": _zeilen(get_user_model().objects.filter(is_active=False)), "archiv": True},
    )


def _startpasswort_zeigen(request, ziel, passwort, neu):
    # Die aufrufenden Ansichten sind never_cache: Das Passwort landet in keinem Zwischenspeicher.
    return render(
        request,
        "konten/startpasswort.html",
        {"ziel": ziel, "passwort": passwort, "neu": neu},
    )


@never_cache
@verwalter_erforderlich
def anlegen(request):
    form = MitarbeiterForm(
        request.POST or None, verwalter=request.user, mail_moeglich=mail.eingerichtet()
    )
    if request.method == "POST" and form.is_valid():
        daten = {f: form.cleaned_data[f] for f in MitarbeiterForm.Meta.fields}
        per_mail = form.cleaned_data.get("zugang") == "einladung"
        # Das Formular bietet nur erlaubte Rollen an; verwaltung.anlegen prüft es trotzdem.
        ziel, passwort = verwaltung.anlegen(
            request.user, daten, form.cleaned_data["rollen"], einladung=per_mail
        )
        if not per_mail:
            return _startpasswort_zeigen(request, ziel, passwort, neu=True)
        try:
            einladung.senden(request, ziel, einladung.EINLADUNG)
        except mail.MailFehler as fehler:
            # Konto gibt es schon; dann eben mit Startpasswort weiter.
            passwort = verwaltung.passwort_zuruecksetzen(request.user, ziel)
            messages.error(request, f"Die Einladung konnte nicht gesendet werden: {fehler}")
            return _startpasswort_zeigen(request, ziel, passwort, neu=True)
        messages.success(request, f"{ziel} ist angelegt. Die Einladung ging an {ziel.email}.")
        return redirect("konten:mitarbeiter", pk=ziel.pk)
    return render(request, "konten/mitarbeiter.html", {"form": form, "ziel": None})


def _ziel(request, pk):
    ziel = get_object_or_404(get_user_model(), pk=pk)
    if not verwaltung.darf_bearbeiten(request.user, ziel):
        raise PermissionDenied
    return ziel


@verwalter_erforderlich
def bearbeiten(request, pk):
    ziel = _ziel(request, pk)
    form = MitarbeiterForm(request.POST or None, instance=ziel, verwalter=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            verwaltung.bearbeiten(request.user, form.instance, form.cleaned_data["rollen"])
        except verwaltung.VerwaltungsFehler as fehler:
            form.add_error("rollen", str(fehler))
        else:
            messages.success(request, f"Änderungen an {ziel} gespeichert.")
            return redirect("konten:mitarbeitende")
    return render(
        request,
        "konten/mitarbeiter.html",
        {
            "form": form,
            "ziel": ziel,
            "zwei_faktor": user_has_device(ziel),
            "mail": mail.eingerichtet(),
        },
    )


def _aktion(request, pk, funktion, erfolg):
    ziel = _ziel(request, pk)
    try:
        funktion(request.user, ziel)
    except verwaltung.VerwaltungsFehler as fehler:
        messages.error(request, str(fehler))
    else:
        messages.success(request, erfolg.format(ziel=ziel))
    return redirect("konten:mitarbeiter", pk=ziel.pk)


@require_POST
@verwalter_erforderlich
def sperren(request, pk):
    return _aktion(
        request, pk, verwaltung.sperren, "{ziel} ist gesperrt und steht jetzt im Archiv."
    )


@require_POST
@verwalter_erforderlich
def entsperren(request, pk):
    return _aktion(request, pk, verwaltung.entsperren, "{ziel} ist wieder aktiv.")


@require_POST
@verwalter_erforderlich
def zwei_faktor_zuruecksetzen(request, pk):
    def zuruecksetzen(verwalter, ziel):
        zwei_faktor.abschalten(ziel)

    return _aktion(
        request,
        pk,
        zuruecksetzen,
        "Zwei-Faktor für {ziel} zurückgesetzt. Bei Pflicht muss es neu eingerichtet werden.",
    )


@require_POST
@verwalter_erforderlich
def link_senden(request, pk):
    """Schickt einen Link zum Festlegen eines neuen Passworts; das alte gilt bis dahin weiter."""
    ziel = _ziel(request, pk)
    try:
        einladung.senden(request, ziel, einladung.ZURUECKSETZEN)
    except mail.MailFehler as fehler:
        messages.error(request, f"Nicht gesendet: {fehler}")
    else:
        messages.success(request, f"Link zum Festlegen eines Passworts an {ziel.email} gesendet.")
    return redirect("konten:mitarbeiter", pk=ziel.pk)


@never_cache
@require_POST
@verwalter_erforderlich
def passwort_zuruecksetzen(request, pk):
    ziel = _ziel(request, pk)
    passwort = verwaltung.passwort_zuruecksetzen(request.user, ziel)
    return _startpasswort_zeigen(request, ziel, passwort, neu=False)
