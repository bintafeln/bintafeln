"""Konten der Ausgabestellen für die Einlass-Tablets (ADR 0059).

Jede Ausgabestelle hat höchstens ein Konto: Anmeldung mit dem Namen der Ausgabestelle und
Passwort, ohne Zwei-Faktor, Rolle Ausgabe, nur Kunden dieser Ausgabestelle. Die Seite zeigt die
Angaben der Ausgabestelle und verwaltet das Konto (Passwort, sperren).
"""

from django.contrib import messages
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from apps.konten import rollen, verwaltung
from apps.konten.forms import StellenKontoForm
from apps.konten.views_mitarbeitende import verwalter_erforderlich
from apps.kunden.models import Ausgabestelle


@verwalter_erforderlich
def liste(request):
    stellen = Ausgabestelle.objects.select_related("konto").order_by("-aktiv", "name")
    return render(request, "konten/stellen.html", {"stellen": stellen})


@never_cache
@sensitive_post_parameters("passwort1", "passwort2")
@verwalter_erforderlich
def stelle(request, pk):
    s = get_object_or_404(Ausgabestelle.objects.prefetch_related("zeiten", "kontakte__benutzer"),
                          pk=pk)  # fmt: skip
    konto = getattr(s, "konto", None)
    form = StellenKontoForm(request.POST or None, neu=konto is None)
    if request.method == "POST" and request.POST.get("aktion") in ("sperren", "entsperren"):
        if konto is None:
            raise PermissionDenied
        aktion = verwaltung.sperren if request.POST["aktion"] == "sperren" else (
            verwaltung.entsperren)  # fmt: skip
        aktion(request.user, konto)
        zustand = "entsperrt" if konto.is_active else "gesperrt"
        messages.success(request, f"Konto von „{s.name}“ {zustand}.")
        return redirect("konten:stelle", pk=s.pk)
    if request.method == "POST" and request.POST.get("aktion") in ("dienstplan_an",
                                                                   "dienstplan_aus"):  # fmt: skip
        s.dienstplan_sichtbar = request.POST["aktion"] == "dienstplan_an"
        s.save(update_fields=["dienstplan_sichtbar"])
        zustand = "eingeschaltet" if s.dienstplan_sichtbar else "ausgeschaltet"
        messages.success(request, f"Dienstplan auf dem Tablet von „{s.name}“ {zustand}.")
        return redirect("konten:stelle", pk=s.pk)
    if request.method == "POST" and form.is_valid():
        if rollen.AUSGABE not in verwaltung.vergebbare_rollen(request.user):
            raise PermissionDenied
        passwort = form.cleaned_data["passwort1"]
        with transaction.atomic():
            if konto is None:
                konto = get_user_model()(username=f"ausgabestelle-{s.pk}", stelle=s)
            konto.first_name = s.name[:150]
            konto.last_name = ""
            try:
                password_validation.validate_password(passwort, konto)
            except ValidationError as fehler:
                form.add_error("passwort1", fehler)
            else:
                konto.set_password(passwort)
                konto.passwort_aendern = False
                konto.save()
                konto.groups.set(Group.objects.filter(name=rollen.AUSGABE))
                konto.ausgabestellen.set([s])
                messages.success(request, f"Konto für „{s.name}“ gespeichert. Anmelden am Tablet: "
                                          f"„{s.name}“ und das neue Passwort.")  # fmt: skip
                return redirect("konten:stelle", pk=s.pk)
    return render(request, "konten/stelle.html", {"s": s, "konto": konto, "form": form})
