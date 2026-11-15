"""Wartezeit aufs Handy (ADR 0090): öffentliche Seite /warten/ für Kunden, ohne Konto.

Anmelden mit Kundennummer und Geburtsdatum der Hauptperson (oder über den QR-Code vom Ausweis);
danach erkennt die Seite das Handy am Cookie. Logik in ``apps/aufruf/handy.py``.
"""

import datetime as dt
import json
from functools import cache
from pathlib import Path

from django.conf import settings
from django.core.cache import cache as zwischenspeicher
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.antraege import sprachen
from apps.aufruf import handy, push
from apps.core.models import TafelEinstellungen

TEXTE = Path(__file__).resolve().parent / "warten_texte"
SPRACH_COOKIE = "bintafeln_warten_sprache"
AKTUALISIEREN = 30  # Sekunden


@cache
def _datei(code: str) -> dict:
    pfad = TEXTE / f"{code}.json"
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


def texte(code: str) -> dict[str, str]:
    return {**_datei("de"), **_datei(code)}


def _ip(request) -> str:
    weitergeleitet = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return weitergeleitet.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def _gesperrt(request) -> bool:
    return zwischenspeicher.get(f"warten-fehl-{_ip(request)}", 0) >= handy.FEHLVERSUCHE


def _fehlversuch(request) -> None:
    schluessel = f"warten-fehl-{_ip(request)}"
    zwischenspeicher.set(schluessel, zwischenspeicher.get(schluessel, 0) + 1, 3600)


def _datum(text: str) -> dt.date | None:
    text = (text or "").strip()
    for muster in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return dt.datetime.strptime(text, muster).date()
        except ValueError:
            continue
    return None


def _zweite(request, z=None):
    """Zweite Sprache neben Deutsch: selbst gewählt, sonst die des Browsers, nach der Anmeldung
    sonst die zur Staatsangehörigkeit der Hauptperson. ``None``: nur Deutsch (auch wenn jemand
    ausdrücklich Deutsch gewählt hat)."""
    gewaehlt = request.GET.get("sprache") or request.COOKIES.get(SPRACH_COOKIE)
    if gewaehlt in sprachen.NACH_CODE:
        code = gewaehlt
    else:
        code = sprachen.aus_browser(request.META.get("HTTP_ACCEPT_LANGUAGE", ""))
        if code == "de" and z is not None:
            code = handy.sprache_vorschlag(z) or "de"
    return None if code == "de" else sprachen.sprache(code)


def _antwort(request, vorlage, kontext, z=None):
    """Seite immer auf Deutsch, darunter jeweils in der zweiten Sprache (``t2``)."""
    s, t = sprachen.sprache("de"), texte("de")
    s2 = _zweite(request, z)
    t2 = texte(s2.code) if s2 else {}
    if kontext.get("fehler"):
        kontext["fehler_text"] = t.get(kontext["fehler"], "")
        kontext["fehler_text2"] = t2.get(kontext["fehler"], "")
    tafel = TafelEinstellungen.laden()
    antwort = render(request, vorlage, {
        **kontext, "s": s, "t": t, "s2": s2, "t2": t2, "wahl": s2.code if s2 else "de",
        "sprachen": sprachen.SPRACHEN, "tafel": tafel, "tafel_name": tafel.name or "Tafel",
        "sprach_hinweise": sprachen.hinweise(), "land_sprache": {},
    })  # fmt: skip
    if request.GET.get("sprache") in sprachen.NACH_CODE:
        antwort.set_cookie(SPRACH_COOKIE, request.GET["sprache"],
                           max_age=handy.COOKIE_TAGE * 86400, samesite="Lax",
                           secure=settings.PRODUKTION)  # fmt: skip
    return antwort


def _stand_texte(stand: dict, t: dict) -> dict:
    """Die Texte zum Stand in einer Sprache (``t``)."""
    texte_ = {"text": t.get(stand["art"], "")}
    if "vor" in stand:
        texte_["vor_text"] = t["vor_ihnen"].format(vor=stand["vor"])
        texte_["vorschau_text"] = t["vorschau"].format(vor=stand["vor"])
    if stand.get("minuten"):
        texte_["minuten_text"] = t["etwa"].format(minuten=stand["minuten"])
    return texte_


def _merken(antwort, schluessel: str):
    antwort.set_cookie(handy.COOKIE, schluessel, max_age=handy.COOKIE_TAGE * 86400,
                       httponly=True, samesite="Lax", secure=settings.PRODUKTION)  # fmt: skip
    return antwort


def _geraet(request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")[:120]


@never_cache
def seite(request):
    z = handy.zugang(request.COOKIES.get(handy.COOKIE, ""))
    fehler = ""
    if request.method == "POST" and z is None:
        if _gesperrt(request):
            fehler = "gesperrt"
        else:
            try:
                schluessel = handy.anmelden(request.POST.get("kundennummer", ""),
                                            _datum(request.POST.get("geburtsdatum", "")),
                                            _geraet(request))  # fmt: skip
            except handy.Abgelehnt as e:
                fehler = e.args[0]
                if fehler == "falsch":
                    _fehlversuch(request)
            else:
                return _merken(redirect("warten:seite"), schluessel)
    if z is None:
        return _antwort(request, "aufruf/warten.html", {"fehler": fehler})
    s2 = _zweite(request, z)
    t, t2 = texte("de"), texte(s2.code) if s2 else {}
    stand = handy.stand(z)
    stand |= _stand_texte(stand, t)
    uhrzeit = timezone.localtime().strftime("%H:%M")
    return _antwort(request, "aufruf/warten_stand.html", {
        "stand": stand, "stand2": _stand_texte(stand, t2) if t2 else {},
        "aktualisieren": AKTUALISIEREN, "uhrzeit": uhrzeit,
        "aktualisiert": t["aktualisiert"].format(uhrzeit=uhrzeit),
        "aktualisiert2": t2["aktualisiert"].format(uhrzeit=uhrzeit) if t2 else "",
        "push": stand["art"] != "nicht_verfuegbar", "push_an": bool(z.push_adresse),
        "push_schluessel": push.oeffentlicher_schluessel() if stand["art"] != "nicht_verfuegbar"
        else "",
    }, z)  # fmt: skip


@require_POST
def abmelden(request):
    handy.abmelden(request.COOKIES.get(handy.COOKIE, ""))
    antwort = redirect("warten:seite")
    antwort.delete_cookie(handy.COOKIE)
    return antwort


@never_cache
def code(request, code):
    """QR-Code vom Ausweis: Handy ohne Geburtsdatum einrichten."""
    if handy.zugang(request.COOKIES.get(handy.COOKIE, "")):
        return redirect("warten:seite")
    if _gesperrt(request):
        return _antwort(request, "aufruf/warten.html", {"fehler": "gesperrt"})
    try:
        schluessel = handy.code_einloesen(code, _geraet(request))
    except handy.Abgelehnt as e:
        if e.args[0] == "code_ungueltig":
            _fehlversuch(request)
        return _antwort(request, "aufruf/warten.html", {"fehler": e.args[0]})
    return _merken(redirect("warten:seite"), schluessel)


# ── Push-Nachrichten (ADR 0134) ─────────────────────────────────────────────


@require_POST
def push_an(request):
    """Der Browser schickt sein Push-Abo; es gilt für das Handy hinter dem Cookie."""
    z = handy.zugang(request.COOKIES.get(handy.COOKIE, ""))
    if z is None:
        return JsonResponse({"ok": False}, status=403)
    try:
        daten = json.loads(request.body or b"{}")
        abo = daten.get("abo") or {}
        schluessel = abo.get("keys") or {}
        sprache = daten.get("sprache") if daten.get("sprache") in sprachen.NACH_CODE else "de"
        push.abonnieren(z, str(abo.get("endpoint", "")), str(schluessel.get("p256dh", "")),
                        str(schluessel.get("auth", "")), sprache)  # fmt: skip
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"ok": False}, status=400)
    return JsonResponse({"ok": True})


@require_POST
def push_aus(request):
    z = handy.zugang(request.COOKIES.get(handy.COOKIE, ""))
    if z is not None:
        push.abbestellen(z)
    return JsonResponse({"ok": True})


@cache
def _sw_quelle() -> str:
    return (Path(__file__).resolve().parent / "warten_sw.js").read_text(encoding="utf-8")


def service_worker(request):
    """Unter /warten/, damit er für die Wartezeit-Seite zuständig ist."""
    quelle = _sw_quelle().replace("__SYMBOL__", reverse("core:app_symbol", args=[192]))
    quelle = quelle.replace("__START__", reverse("warten:seite"))
    antwort = HttpResponse(quelle, content_type="application/javascript; charset=utf-8")
    antwort["Cache-Control"] = "no-cache"
    return antwort


def manifest(request):
    """Eigenes Manifest: Vom Startbildschirm öffnet sich die Wartezeit, nicht die Anmeldung der
    Mitarbeitenden (auf dem iPhone gehen Push-Nachrichten nur so)."""
    tafel = TafelEinstellungen.laden()
    name = f"{texte('de')['titel']} – {tafel.name or 'Tafel'}"
    return JsonResponse({
        "name": name, "short_name": (tafel.name or texte("de")["titel"])[:12],
        "start_url": reverse("warten:seite"), "scope": reverse("warten:seite"),
        "display": "standalone", "theme_color": tafel.farbe, "background_color": "#ffffff",
        "icons": [{"src": reverse("core:app_symbol", args=[g]), "sizes": f"{g}x{g}",
                   "type": "image/png"} for g in (192, 512)],
    }, content_type="application/manifest+json")  # fmt: skip
