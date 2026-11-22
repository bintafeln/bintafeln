"""Push-Nachrichten an Mitarbeitende (ADR 0158): ein- und ausschalten je Gerät, nur auf „Mein
Konto“. Die Technik steht in ``apps/core/push.py``."""

import json
from functools import cache
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core import push
from apps.core.models import PushAbo
from bintafeln import programm


@cache
def _sw_quelle() -> str:
    return (Path(__file__).resolve().parent / "push_sw.js").read_text(encoding="utf-8")


def service_worker(request):
    """Öffentlich und ganz oben (/push-sw.js), damit er für alle Seiten zuständig sein darf; er
    enthält nichts Vertrauliches."""
    quelle = _sw_quelle().replace("__SYMBOL__", reverse("core:app_symbol", args=[192]))
    quelle = quelle.replace("__START__", reverse("core:start"))
    antwort = HttpResponse(quelle, content_type="application/javascript; charset=utf-8")
    antwort["Cache-Control"] = "no-cache"
    return antwort


def _abo(request) -> tuple[str, str, str]:
    abo = json.loads(request.body or b"{}").get("abo") or {}
    schluessel = abo.get("keys") or {}
    return (str(abo.get("endpoint", "")), str(schluessel.get("p256dh", "")),
            str(schluessel.get("auth", "")))  # fmt: skip


@login_required
@require_POST
def an(request):
    """Der Browser schickt sein Push-Abo; es gilt für dieses Gerät und das angemeldete Konto."""
    try:
        adresse, p256dh, auth = _abo(request)
        push.abonnieren(request.user, adresse, p256dh, auth,
                        request.META.get("HTTP_USER_AGENT", ""))  # fmt: skip
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"ok": False}, status=400)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def aus(request):
    try:
        adresse = _abo(request)[0]
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"ok": False}, status=400)
    if adresse:
        push.abbestellen(request.user, adresse)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def stand(request):
    """Ist dieses Gerät für das angemeldete Konto eingeschaltet? (Ein Gerät kann vorher zu einem
    anderen Konto gehört haben.)"""
    try:
        adresse = _abo(request)[0]
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"an": False}, status=400)
    an = bool(adresse) and PushAbo.objects.filter(
        benutzer=request.user, adresse=adresse[:2000]
    ).exists()  # fmt: skip
    return JsonResponse({"an": an})


@login_required
@require_POST
def probe(request):
    """Probe-Nachricht an die eigenen Geräte."""
    gesendet = push.an_benutzer(
        request.user, programm.NAME, "So sehen Nachrichten auf diesem Gerät aus.",
        link=reverse("konten:mein_konto"), kennung="probe",
    )  # fmt: skip
    return JsonResponse({"ok": gesendet > 0, "gesendet": gesendet})
