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
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.antraege import sprachen
from apps.aufruf import handy
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


def _sprache(request):
    wahl = (request.GET.get("sprache") or request.COOKIES.get(SPRACH_COOKIE)
            or sprachen.aus_browser(request.META.get("HTTP_ACCEPT_LANGUAGE", "")))  # fmt: skip
    return sprachen.sprache(wahl)


def _antwort(request, vorlage, kontext):
    s = _sprache(request)
    t = texte(s.code)
    if kontext.get("fehler"):
        kontext["fehler_text"] = t.get(kontext["fehler"], "")
    tafel = TafelEinstellungen.laden()
    antwort = render(request, vorlage, {
        **kontext, "s": s, "t": t, "sprachen": sprachen.SPRACHEN, "tafel": tafel,
        "tafel_name": tafel.name or "Tafel", "sprach_hinweise": sprachen.hinweise(),
        "land_sprache": {},
    })  # fmt: skip
    if request.GET.get("sprache") in sprachen.NACH_CODE:
        antwort.set_cookie(SPRACH_COOKIE, s.code, max_age=handy.COOKIE_TAGE * 86400,
                           samesite="Lax", secure=settings.PRODUKTION)  # fmt: skip
    return antwort


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
    s = _sprache(request)
    t = texte(s.code)
    stand = handy.stand(z)
    stand["text"] = t.get(stand["art"], "")
    if "vor" in stand:
        stand["vor_text"] = t["vor_ihnen"].format(vor=stand["vor"])
        stand["vorschau_text"] = t["vorschau"].format(vor=stand["vor"])
    if stand.get("minuten"):
        stand["minuten_text"] = t["etwa"].format(minuten=stand["minuten"])
    uhrzeit = timezone.localtime().strftime("%H:%M")
    # Sprache zur Staatsangehörigkeit vorschlagen, solange niemand selbst gewählt hat
    gewaehlt = request.GET.get("sprache") or request.COOKIES.get(SPRACH_COOKIE)
    return _antwort(request, "aufruf/warten_stand.html", {
        "stand": stand, "aktualisieren": AKTUALISIEREN,
        "aktualisiert": t["aktualisiert"].format(uhrzeit=uhrzeit),
        "vorschlag": "" if gewaehlt else handy.sprache_vorschlag(z),
    })  # fmt: skip


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
