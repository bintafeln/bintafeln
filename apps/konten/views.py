import logging
from functools import wraps

from django.conf import settings
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
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django_otp import login as otp_login
from django_otp import match_token

from apps.core import mail
from apps.konten import einladung, rollen, zwei_faktor
from apps.konten.forms import AnmeldeEinstellungenForm, AnmeldeForm, CodeForm, ZweiterSchrittForm
from apps.konten.models import AnmeldeEinstellungen, VertrautesGeraet

logger = logging.getLogger(__name__)


def _ziel(request) -> str:
    ziel = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        ziel, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return ziel
    return "core:start"


SITZUNG_ZWEITER_SCHRITT = "anmeldung_zweiter_schritt"
ZWEITER_SCHRITT_MINUTEN = 5
ZWEITER_SCHRITT_VERSUCHE = 5


@sensitive_post_parameters("password")
def anmelden(request):
    """Schritt 1: Benutzername und Passwort. Mit Zwei-Faktor-Gerät weiter zu Schritt 2."""
    if request.user.is_authenticated:
        return redirect("core:start")
    form = AnmeldeForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.braucht_code:
            request.session.cycle_key()
            request.session[SITZUNG_ZWEITER_SCHRITT] = {
                "b": form.benutzer.pk, "backend": form.benutzer.backend,
                "zeit": timezone.now().timestamp(), "next": _ziel(request), "versuche": 0,
            }  # fmt: skip
            return redirect("konten:anmelden_code")
        login(request, form.benutzer)
        if form.geraet is not None:
            otp_login(request, form.geraet)
        return redirect(_ziel(request))
    return render(
        request,
        "konten/anmelden.html",
        {
            "form": form,
            "next": request.GET.get("next", ""),
            "mail": mail.eingerichtet(),
            **_demo_zugaenge(),
        },
    )


@sensitive_post_parameters("otp_token")
def anmelden_code(request):
    """Schritt 2: Zwei-Faktor-Code. Gilt nur kurz nach Schritt 1 und für wenige Versuche."""
    if request.user.is_authenticated:
        return redirect("core:start")
    offen = request.session.get(SITZUNG_ZWEITER_SCHRITT)
    benutzer = None
    if offen and timezone.now().timestamp() - offen["zeit"] < ZWEITER_SCHRITT_MINUTEN * 60:
        benutzer = get_user_model().objects.filter(pk=offen["b"], is_active=True).first()
    if benutzer is None:
        request.session.pop(SITZUNG_ZWEITER_SCHRITT, None)
        messages.error(request, "Bitte zuerst Benutzername und Passwort eingeben.")
        return redirect("konten:anmelden")
    form = ZweiterSchrittForm(benutzer, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            request.session.pop(SITZUNG_ZWEITER_SCHRITT, None)
            login(request, benutzer, backend=offen["backend"])
            otp_login(request, form.geraet)
            antwort = redirect(offen["next"])
            if form.cleaned_data.get("vertrauen"):
                zwei_faktor.geraet_vertrauen(request, antwort, benutzer)
            return antwort
        offen["versuche"] += 1
        if offen["versuche"] >= ZWEITER_SCHRITT_VERSUCHE:
            request.session.pop(SITZUNG_ZWEITER_SCHRITT, None)
            messages.error(request, "Zu viele falsche Codes. Bitte neu anmelden.")
            return redirect("konten:anmelden")
        request.session[SITZUNG_ZWEITER_SCHRITT] = offen
    return render(request, "konten/anmelden_code.html", {"form": form, "benutzer": benutzer})


def _demo_zugaenge() -> dict:
    if not settings.DEMO:
        return {}
    from apps.core.demo import KONTEN, tablet_zugang

    konten = [(name, " und ".join(namen)) for name, _, _, namen, _ in KONTEN]
    tablet = tablet_zugang()
    return {
        "demo_konten": konten + ([tablet] if tablet else []),
        "demo_passwort": settings.DEMO_PASSWORT,
    }


def nicht_in_demo(ansicht):
    """In der öffentlichen Demo gesperrt, damit niemand andere Besucher aussperrt."""

    @wraps(ansicht)
    def pruefen(request, *args, **kwargs):
        if settings.DEMO:
            messages.error(request, "In der Demoversion nicht möglich.")
            return redirect("konten:mein_konto")
        return ansicht(request, *args, **kwargs)

    return pruefen


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
@nicht_in_demo
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
            "geraete": _vertraute_geraete(request.user),
            "vertrauen_tage": zwei_faktor.vertrauen_tage(),
        },
    )


def _vertraute_geraete(benutzer):
    zwei_faktor.geraete_aufraeumen()
    return benutzer.vertraute_geraete.all()


@login_required
@require_POST
def geraet_entfernen(request, pk=None):
    """Ein vertrautes Gerät (oder alle) des eigenen Kontos entfernen."""
    geraete = request.user.vertraute_geraete.all()
    if pk is not None:
        geraete = geraete.filter(pk=pk)
    anzahl = geraete.delete()[0]
    if anzahl:
        messages.success(request, "Entfernt. Dort ist bei der nächsten Anmeldung wieder ein Code "
                         "nötig." if pk else "Alle vertrauten Geräte entfernt.")  # fmt: skip
    return redirect("konten:mein_konto")


def _codes_anzeigen(request, codes):
    antwort = render(request, "konten/notfallcodes.html", {"codes": codes})
    add_never_cache_headers(antwort)
    return antwort


@never_cache
@login_required
@nicht_in_demo
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


@never_cache
@rollen.recht_erforderlich("einstellungen.rollen")
def anmelde_einstellungen(request):
    form = AnmeldeEinstellungenForm(request.POST or None, instance=AnmeldeEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        if not form.instance.vertrauen_tage:
            VertrautesGeraet.objects.all().delete()  # ausgeschaltet: niemand bleibt vertraut
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("konten:anmelde_einstellungen")
    anzahl = VertrautesGeraet.objects.filter(gueltig_bis__gt=timezone.now()).count()
    return render(request, "konten/anmelde_einstellungen.html", {"form": form, "anzahl": anzahl})
