from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from django_otp import login as otp_login

from apps.konten.forms import AnmeldeForm


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
