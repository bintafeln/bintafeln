import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import PasswordResetConfirmView
from django.core.cache import cache
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.cache import add_never_cache_headers
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django_otp import login as otp_login
from django_otp import match_token

from apps.core import mail
from apps.konten import einladung, zwei_faktor
from apps.konten.forms import AnmeldeForm, CodeForm

logger = logging.getLogger(__name__)


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
        request,
        "konten/anmelden.html",
        {"form": form, "next": request.GET.get("next", ""), "mail": mail.eingerichtet()},
    )


VERGESSEN_SPERRE = 5 * 60  # höchstens eine Mail je Konto in fünf Minuten


@sensitive_post_parameters("eingabe")
def passwort_vergessen(request):
    """Schickt einen Link zum Zurücksetzen. Verrät nie, ob es das Konto gibt."""
    if not mail.eingerichtet():
        raise Http404
    if request.method == "POST":
        eingabe = request.POST.get("eingabe", "").strip()
        if eingabe:
            treffer = (
                get_user_model()
                .objects.filter(
                    Q(username__iexact=eingabe) | Q(email__iexact=eingabe), is_active=True
                )
                .exclude(email="")
            )
            for benutzer in treffer:
                if cache.add(f"passwort-vergessen:{benutzer.pk}", True, VERGESSEN_SPERRE):
                    try:
                        einladung.senden(request, benutzer, einladung.ZURUECKSETZEN)
                    except mail.MailFehler:
                        logger.warning(
                            "Mail zum Zurücksetzen nicht gesendet (Konto %s)", benutzer.pk
                        )
        messages.info(
            request,
            "Falls es dazu ein Konto mit hinterlegter E-Mail-Adresse gibt, ist eine Mail mit "
            "einem Link unterwegs. Bitte auch im Spam-Ordner nachsehen.",
        )
        return redirect("konten:anmelden")
    return render(request, "konten/passwort_vergessen.html")


class PasswortSetzen(PasswordResetConfirmView):
    """Neues Passwort über den Link aus Einladung oder Zurücksetzen-Mail."""

    template_name = "konten/passwort_setzen.html"
    success_url = reverse_lazy("konten:anmelden")

    def form_valid(self, form):
        antwort = super().form_valid(form)
        form.user.passwort_aendern = False
        form.user.save(update_fields=["passwort_aendern"])
        messages.success(self.request, "Ihr Passwort ist gespeichert. Bitte jetzt anmelden.")
        return antwort


@require_POST
def abmelden(request):
    logout(request)
    return redirect("konten:anmelden")


@never_cache
@login_required
@sensitive_post_parameters("old_password", "new_password1", "new_password2")
def passwort_aendern(request):
    """Eigenes Passwort ändern; Pflicht nach einem Startpasswort."""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        benutzer = form.save(commit=False)
        benutzer.passwort_aendern = False
        benutzer.save()
        update_session_auth_hash(request, benutzer)  # angemeldet bleiben
        messages.success(request, "Ihr Passwort wurde geändert.")
        return redirect("core:start")
    return render(
        request,
        "konten/passwort_aendern.html",
        {"form": form, "pflicht": request.user.passwort_aendern},
    )


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
