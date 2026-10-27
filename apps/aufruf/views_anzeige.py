"""Anzeige-Geräte ohne Anmeldung (Monitor, Nummern-Anzeige, Kiosk, Abfrage), ADR 0050.

Zugang nur über den geheimen Schlüssel der Ausgabestelle im Link (``AufrufEinstellungen``).
Die Seiten zeigen Kundennummern, nie Namen. Neu erzeugen des Schlüssels sperrt alte Links.
"""

import json

from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_http_methods

from apps.aufruf import ablauf
from apps.aufruf.models import LAYOUT_GRENZEN, LAYOUT_STANDARD, AufrufEinstellungen, AufrufInfo
from apps.aufruf.views import plaetze

# Namen im Skript des Monitors (bisheriges Layout-Panel) ↔ gespeicherte Namen
LAYOUT_JS = {
    "nextCustomers": "next_customers_width", "currentNumbers": "current_numbers_width",
    "infoDisplay": "info_display_width", "headerHeight": "header_height",
    "headerFont": "header_font", "nextCustomersFont": "next_customers_font",
    "currentNumbersFont": "current_numbers_font", "infoDisplayFont": "info_display_font",
}  # fmt: skip


def _einstellungen(schluessel) -> AufrufEinstellungen:
    e = get_object_or_404(AufrufEinstellungen.objects.select_related("ausgabestelle"),
                          schluessel=schluessel)  # fmt: skip
    if not e.ausgabestelle.aktiv:
        raise Http404
    return e


def _urls(e, monitor=False) -> dict:
    k = e.schluessel
    stand = reverse("aufruf:anzeige_stand", args=[k])
    return {
        "stand": f"{stand}?monitor=1" if monitor else stand,
        "abfrage": reverse("aufruf:anzeige_abfrage", args=[k]),
        "layout": reverse("aufruf:anzeige_layout", args=[k]),
        "anzeige": reverse("aufruf:anzeige", args=[k]),
    }


def infos(e) -> list[AufrufInfo]:
    stelle = e.ausgabestelle
    return list(AufrufInfo.objects.filter(aktiv=True)
                .filter(Q(ausgabestellen=None) | Q(ausgabestellen=stelle)).distinct())  # fmt: skip


def _info_daten(e, info) -> dict:
    url = (
        info.adresse
        if info.art == AufrufInfo.Art.WEBSEITE
        else (reverse("aufruf:anzeige_datei", args=[e.schluessel, info.pk]) if info.datei else "")
    )
    return {"id": info.pk, "art": info.art, "titel": info.titel, "text": info.text,
            "url": url, "dauer": info.dauer}  # fmt: skip


def _kontext(e, monitor=False, **mehr) -> dict:
    return {"stelle": e.ausgabestelle, "urls": _urls(e, monitor), "anzahl": e.anzahl, **mehr}


@never_cache
def anzeige(request, schluessel):
    return render(request, "aufruf/anzeige.html", _kontext(_einstellungen(schluessel)))


@never_cache
def monitor(request, schluessel):
    e = _einstellungen(schluessel)
    heute = timezone.localdate()
    # Der große Monitor zeigt Aufgerufene bis zum nächsten „Weiter“, auch wenn schon eingelassen
    d = ablauf.stand_fuer_anzeige(ablauf.aktualisieren(e.ausgabestelle, heute), e, heute,
                                  eingelassene_zeigen=True)  # fmt: skip
    if "error" in d:
        return render(request, "aufruf/monitor_wartet.html", _kontext(e, monitor=True))
    if d["finished"]:
        return render(request, "aufruf/monitor_fertig.html", _kontext(e, monitor=True, **d))
    return render(request, "aufruf/monitor.html", _kontext(
        e, monitor=True, **d, plaetze=plaetze(d["current_numbers"], d["priority_flags"], e.anzahl),
        layout={k: str(v) for k, v in e.layout_werte().items()},
        infos=[_info_daten(e, i) for i in infos(e)] if e.info_rotation else [],
        info_rotation=e.info_rotation,
    ))  # fmt: skip


@never_cache
def abfrage(request, schluessel):
    return render(request, "aufruf/abfrage.html", _kontext(_einstellungen(schluessel)))


@never_cache
def kiosk(request, schluessel):
    return render(request, "aufruf/kiosk.html", _kontext(_einstellungen(schluessel)))


@never_cache
def stand(request, schluessel):
    e = _einstellungen(schluessel)
    heute = timezone.localdate()
    monitor_ = request.GET.get("monitor") == "1"  # großer Monitor: Aufgerufene bleiben stehen
    d = ablauf.stand_fuer_anzeige(ablauf.aktualisieren(e.ausgabestelle, heute), e, heute,
                                  eingelassene_zeigen=monitor_)  # fmt: skip
    for schluessel_ in (
        "present_flags",
        "next_present_flags",
        "past_present_flags",
        "kiosk_numbers",
    ):
        d.pop(schluessel_, None)  # wer schon da ist, sieht nur das Team
    if "error" not in d:
        d["infos"] = [{"id": i.pk} for i in infos(e)] if e.info_rotation else []
        d["info_settings"] = {"rotation_enabled": e.info_rotation}
    return JsonResponse(d)


@never_cache
def abfrage_api(request, schluessel):
    e = _einstellungen(schluessel)
    nummer = request.GET.get("nummer", "").strip()[:20]
    if not nummer:
        return JsonResponse({"error": "Keine Kundennummer angegeben"}, status=400)
    heute = timezone.localdate()
    daten = ablauf.abfrage(e.ausgabestelle, heute, nummer)
    # Am Kiosk gescannt (nicht die Abfrage-Seite): Der Kunde ist da – grün in der Steuerung
    if request.GET.get("kiosk") and daten.get("gefunden") and not daten.get("abgeholt"):
        ablauf.kiosk_melden(e.ausgabestelle, heute, nummer)
    daten.pop("abgeholt_um", None)  # Geräte ohne Anmeldung: keine Uhrzeit der Abholung
    return JsonResponse(daten)


def layout_pruefen(daten: dict) -> dict:
    """Wie bisher: Breiten auf 100 % bringen, alle Werte in ihre Grenzen."""
    werte = {}
    for js, name in LAYOUT_JS.items():
        roh = daten.get(js, daten.get(name, LAYOUT_STANDARD[name]))
        try:
            wert = float(roh)
        except (TypeError, ValueError):
            wert = LAYOUT_STANDARD[name]
        werte[name] = wert
    breiten = ["next_customers_width", "current_numbers_width", "info_display_width"]
    summe = sum(werte[b] for b in breiten) or 100
    if summe != 100:
        for b in breiten:
            werte[b] = round(werte[b] / summe * 100)
        werte["info_display_width"] += 100 - sum(werte[b] for b in breiten)
    for name, (klein, gross) in LAYOUT_GRENZEN.items():
        werte[name] = max(klein, min(gross, werte[name]))
        if isinstance(LAYOUT_STANDARD[name], int):
            werte[name] = int(round(werte[name]))
        else:
            werte[name] = round(werte[name], 1)
    return werte


@never_cache
@require_http_methods(["GET", "POST"])
def layout(request, schluessel):
    """Aufteilung des Monitors (das Zahnrad am Monitor speichert hier)."""
    e = _einstellungen(schluessel)
    if request.method == "POST":
        try:
            daten = json.loads(request.body or b"{}")
        except ValueError:
            return JsonResponse({"success": False, "error": "Keine gültigen Daten"}, status=400)
        if not isinstance(daten, dict):
            return JsonResponse({"success": False, "error": "Keine gültigen Daten"}, status=400)
        e.layout = layout_pruefen(daten)
        e.save(update_fields=["layout"])
    werte = e.layout_werte()
    return JsonResponse(
        {
            "success": True,
            "message": "Layout-Einstellungen gespeichert",
            "layout": {js: werte[name] for js, name in LAYOUT_JS.items()},
        }
    )


@xframe_options_sameorigin
def datei(request, schluessel, pk):
    """Bild oder PDF einer Info, nur für Monitore mit gültigem Schlüssel."""
    e = _einstellungen(schluessel)
    info = get_object_or_404(AufrufInfo, pk=pk, aktiv=True)
    if info not in infos(e) or not info.datei:
        raise Http404
    try:
        return FileResponse(info.datei.open("rb"), filename=info.datei.name.rsplit("/", 1)[-1])
    except FileNotFoundError as fehler:
        raise Http404 from fehler
