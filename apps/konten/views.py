from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.cache import add_never_cache_headers
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django_otp import login as otp_login
from django_otp import match_token

from apps.konten import zwei_faktor
from apps.konten.forms import AnmeldeForm, CodeForm


def _ziel(request) -> str:
    ziel = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        ziel, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return ziel
    return "core:start"


@sensitive_post_parameters("password", "otp_token")
def anmelden(request):
    if request.user.is_authenticated:
        return redirect("core:start")
    form = AnmeldeForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.benutzer)
        if form.geraet is not None:
            otp_login(request, form.geraet)
        return redirect(_ziel(request))
    return render(
        request, "konten/anmelden.html", {"form": form, "next": request.GET.get("next", "")}
    )


@require_POST
def abmelden(request):
    logout(request)
    return redirect("konten:anmelden")


@login_required
def mein_konto(request):
    return render(
        request,
        "konten/mein_konto.html",
        {
            "zwei_faktor_aktiv": zwei_faktor.app_geraet(request.user) is not None,
            "zwei_faktor_pflicht": zwei_faktor.ist_pflicht(request.user),
            "notfallcodes_uebrig": zwei_faktor.notfallcodes_uebrig(request.user),
            "form": CodeForm(),
        },
    )


def _codes_anzeigen(request, codes):
    antwort = render(request, "konten/notfallcodes.html", {"codes": codes})
    add_never_cache_headers(antwort)
    return antwort


@never_cache
@login_required
@sensitive_post_parameters("code")
def zwei_faktor_einrichten(request):
    if zwei_faktor.app_geraet(request.user) is not None:
        return redirect("konten:mein_konto")
    geraet = zwei_faktor.neues_app_geraet(request.user)
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if zwei_faktor.einrichtung_bestaetigen(geraet, form.cleaned_data["code"]):
            otp_login(request, geraet)
            messages.success(request, "Zwei-Faktor-Anmeldung ist eingerichtet.")
            return _codes_anzeigen(request, zwei_faktor.notfallcodes_erzeugen(request.user))
        form.add_error("code", "Der Code stimmt nicht. Bitte den aktuellen Code der App eingeben.")
    return render(
        request,
        "konten/zwei_faktor_einrichten.html",
        {
            "form": form,
            "qr_code": mark_safe(zwei_faktor.qr_code_svg(geraet)),  # noqa: S308 – selbst erzeugt
            "schluessel": zwei_faktor.schluessel_als_text(geraet),
            "einrichtungs_link": geraet.config_url,
            "pflicht": zwei_faktor.ist_pflicht(request.user),
        },
    )


@require_POST
@login_required
def notfallcodes_neu(request):
    if zwei_faktor.app_geraet(request.user) is None:
        return redirect("konten:mein_konto")
    return _codes_anzeigen(request, zwei_faktor.notfallcodes_erzeugen(request.user))


@require_POST
@login_required
@sensitive_post_parameters("code")
def zwei_faktor_abschalten(request):
    if zwei_faktor.ist_pflicht(request.user):
        messages.error(request, "Für Ihre Rolle ist die Zwei-Faktor-Anmeldung Pflicht.")
        return redirect("konten:mein_konto")
    form = CodeForm(request.POST)
    if form.is_valid() and match_token(
        request.user, zwei_faktor.code_bereinigen(form.cleaned_data["code"])
    ):
        zwei_faktor.abschalten(request.user)
        messages.success(request, "Zwei-Faktor-Anmeldung wurde abgeschaltet.")
    else:
        messages.error(request, "Der Code stimmt nicht. Zwei-Faktor bleibt eingeschaltet.")
    return redirect("konten:mein_konto")
