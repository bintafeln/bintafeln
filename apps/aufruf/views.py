"""Steuerung des Aufrufs (angemeldet, Recht ``aufruf.steuern``): Seite, Handy und Schnittstellen.

Die Seiten sind aus dem bisherigen Aufrufsystem übernommen; ihre Skripte erwarten die
Antworten im bisherigen Format (``ablauf.stand_fuer_anzeige``).
"""

import csv
import json
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.aufruf import ablauf
from apps.aufruf.models import AufrufEinstellungen
from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import Ausgabestelle

steuern = rollen.recht_erforderlich("aufruf.steuern")


def stellen_fuer(benutzer):
    eigene = zugang.stellen(benutzer)
    # Nur Ausgabestellen, an denen aufgerufen wird (ohne Einstellungen gilt: ja)
    stellen = Ausgabestelle.objects.filter(aktiv=True).exclude(aufruf__aktiv=False)
    return stellen.filter(pk__in=[s.pk for s in eigene]) if eigene is not None else stellen


def _stelle(request, pk) -> Ausgabestelle:
    stelle = get_object_or_404(Ausgabestelle, pk=pk, aktiv=True)
    if not stellen_fuer(request.user).filter(pk=stelle.pk).exists():
        raise PermissionDenied(f"Sie sind der Ausgabestelle „{stelle.name}“ nicht zugeordnet.")
    return stelle


def plaetze(nummern, flags, anzahl) -> list[dict]:
    """Feste Anzahl Plätze für „Bitte eintreten“ (leere mit Strich)."""
    return [{"nummer": nummern[i] if i < len(nummern) else "",
             "vorrang": i < len(flags) and flags[i]} for i in range(anzahl)]  # fmt: skip


def _urls(stelle, einstellungen) -> dict:
    def r(name, *args):
        return reverse(f"aufruf:{name}", args=args)

    k = einstellungen.schluessel
    return {
        "stand": r("api_stand", stelle.pk), "status": r("api_status", stelle.pk),
        "starten": r("api_starten", stelle.pk), "weiter": r("api_weiter", stelle.pk),
        "zurueck": r("api_zurueck", stelle.pk), "abfrage": r("api_abfrage", stelle.pk),
        "spaetzuender": r("api_spaetzuender", stelle.pk),
        "starten_formular": r("starten", stelle.pk), "weiter_formular": r("weiter", stelle.pk),
        "zurueck_formular": r("zurueck", stelle.pk), "neustart_formular": r("neustart", stelle.pk),
        "mobil": r("mobil", stelle.pk), "liste": r("liste", stelle.pk),
        "anzeige": r("anzeige", k), "monitor": r("monitor", k),
        "abmelden": reverse("konten:abmelden"), "zurueck_bintafeln": reverse("core:start"),
    }  # fmt: skip


@steuern
def start(request):
    """Ausgabestelle wählen; bei nur einer gleich zur Steuerung."""
    stellen = list(stellen_fuer(request.user))
    if len(stellen) == 1:
        return redirect("aufruf:steuerung", stellen[0].pk)
    return render(request, "aufruf/start.html", {"stellen": stellen})


@never_cache
@steuern
def steuerung(request, pk):
    stelle = _stelle(request, pk)
    e = AufrufEinstellungen.laden(stelle)
    heute = timezone.localdate()
    tag = ablauf.aktualisieren(stelle, heute)
    d = ablauf.stand_fuer_anzeige(tag, e, heute)
    kontext = {"stelle": stelle, "urls": _urls(stelle, e), "anzahl": e.anzahl, "heute": heute,
               "current_day": ablauf.tagname(stelle, heute)}  # fmt: skip
    if "error" in d:
        gruppen = ablauf.gruppen_heute(stelle, heute)
        return render(request, "aufruf/tag_starten.html", {
            **kontext, "gruppen": gruppen,
            "available_days": [kontext["current_day"]] if gruppen else [],
        })  # fmt: skip
    if d["finished"]:
        return render(request, "aufruf/fertig.html", {
            **kontext, "selected_day": d["selected_day"], "total_completed": d["total_completed"],
        })  # fmt: skip
    vorschau = d["next_numbers"][:5]
    slot = 100 * d["slot_completed"] / d["slot_total"] if d["slot_total"] else 0
    gesamt = 100 * d["total_completed"] / d["total_numbers"] if d["total_numbers"] else 0
    return render(request, "aufruf/steuerung.html", {
        **kontext, **d,
        "plaetze": plaetze(d["current_numbers"], d["priority_flags"], e.anzahl),
        "has_any_priority": any(d["priority_flags"]),
        "vorschau_nummern": vorschau + [""] * (5 - len(vorschau)),
        "slot_progress": f"{slot:.1f}", "slot_progress_text": f"{slot:.1f}".replace(".", ","),
        "total_progress": f"{gesamt:.1f}", "total_progress_text": f"{gesamt:.1f}".replace(".", ","),
    })  # fmt: skip


@never_cache
@steuern
def mobil(request, pk):
    stelle = _stelle(request, pk)
    e = AufrufEinstellungen.laden(stelle)
    return render(request, "aufruf/mobil.html", {
        "stelle": stelle, "urls": _urls(stelle, e), "anzahl": e.anzahl,
        "spaetzuender_versatz": e.spaetzuender_versatz,
    })  # fmt: skip


def _formular(aktion):
    @require_POST
    @steuern
    def ansicht(request, pk):
        stelle = _stelle(request, pk)
        try:
            aktion(stelle, timezone.localdate())
        except ablauf.AufrufFehler as fehler:
            messages.error(request, str(fehler))
        return redirect("aufruf:steuerung", stelle.pk)

    return ansicht


starten = _formular(ablauf.starten)
weiter = _formular(ablauf.weiter)
zurueck = _formular(ablauf.zurueck)
neustart = _formular(ablauf.neu_mischen)


# ── Schnittstellen für die Skripte (bisheriges Antwortformat) ───────────────


@never_cache
@steuern
def api_stand(request, pk):
    stelle = _stelle(request, pk)
    heute = timezone.localdate()
    tag = ablauf.aktualisieren(stelle, heute)
    return JsonResponse(ablauf.stand_fuer_anzeige(tag, AufrufEinstellungen.laden(stelle), heute))


@never_cache
@steuern
def api_status(request, pk):
    stelle = _stelle(request, pk)
    heute = timezone.localdate()
    tag = ablauf.tag_holen(stelle, heute)
    tagname = ablauf.tagname(stelle, heute)
    return JsonResponse({
        "current_day": tagname, "current_date": heute.isoformat(),
        "available_days": [tagname] if ablauf.gruppen_heute(stelle, heute) else [],
        "has_active_session": bool(tag and tag.gestartet_am),
        "session_day": tagname if tag else None,
        "can_undo": bool(tag and tag.gestartet_am and tag.stand.get("rueckgaengig")),
    })  # fmt: skip


def _antwort_nach_schritt(tag, e, heute, **mehr) -> dict:
    d = ablauf.stand_fuer_anzeige(tag, e, heute)
    antwort = {"success": True, "can_undo": d.get("can_undo", False),
               "total_completed": d.get("total_completed"), "total_numbers": d.get("total_numbers"),
               **mehr}  # fmt: skip
    if d.get("finished"):
        return {
            **antwort,
            "all_finished": True,
            "message": antwort.get("message", "") + " - Alle Kundengruppen abgeschlossen!",
        }
    return {**antwort, "all_finished": False, "current_numbers": d["current_numbers"],
            "current_slot": d["current_slot"], "priority_flags": d["priority_flags"],
            "upcoming_numbers": d["upcoming_numbers"], "remaining_in_slot": d["remaining_count"],
            "slot_completed": d["slot_completed"], "slot_total": d["slot_total"]}  # fmt: skip


def _api(aktion):
    @never_cache
    @require_POST
    @steuern
    def ansicht(request, pk):
        stelle = _stelle(request, pk)
        heute = timezone.localdate()
        try:
            return JsonResponse(aktion(request, stelle, heute))
        except ablauf.AufrufFehler as fehler:
            tag = ablauf.tag_holen(stelle, heute)
            return JsonResponse({"success": False, "error": str(fehler),
                                 "can_undo": bool(tag and tag.stand.get("rueckgaengig"))},
                                status=400)  # fmt: skip

    return ansicht


@_api
def api_starten(request, stelle, heute):
    tag = ablauf.starten(stelle, heute)
    return _antwort_nach_schritt(
        tag,
        AufrufEinstellungen.laden(stelle),
        heute,
        message=f"Tag {ablauf.tagname(stelle, heute)} gestartet",
    )


@_api
def api_weiter(request, stelle, heute):
    vorher = ablauf.tag_holen(stelle, heute)
    vorher_n = sum(len(g["aufgerufen"]) for g in vorher.stand["gruppen"]) if vorher else 0
    tag = ablauf.weiter(stelle, heute)
    anzahl = sum(len(g["aufgerufen"]) for g in tag.stand["gruppen"]) - vorher_n
    return _antwort_nach_schritt(
        tag,
        AufrufEinstellungen.laden(stelle),
        heute,
        message=f"{anzahl} Kundennummer(n) bearbeitet",
    )


@_api
def api_zurueck(request, stelle, heute):
    tag = ablauf.zurueck(stelle, heute)
    return _antwort_nach_schritt(
        tag, AufrufEinstellungen.laden(stelle), heute, message="Letzte Aktion rückgängig gemacht"
    )


@_api
def api_spaetzuender(request, stelle, heute):
    try:
        nummer = str(json.loads(request.body or b"{}").get("nummer", "")).strip()
    except (ValueError, AttributeError):
        nummer = ""
    if not nummer:
        raise ablauf.AufrufFehler("Keine Kundennummer angegeben.")
    e = ablauf.spaetzuender(stelle, heute, nummer)
    if e["bereits"]:
        text = f"Kunde {nummer} wurde bereits neu einsortiert."
    else:
        text = (f"Kunde {nummer} wurde {e['versatz']} Plätze später einsortiert "
                f"(neuer Platz {e['neuer_platz']}).")  # fmt: skip
    return {"success": True, "nummer": ablauf.norm(nummer), "message": text, **e}


@never_cache
@steuern
def api_abfrage(request, pk):
    stelle = _stelle(request, pk)
    nummer = request.GET.get("nummer", "").strip()
    if not nummer:
        return JsonResponse({"error": "Keine Kundennummer angegeben"}, status=400)
    return JsonResponse(ablauf.abfrage(stelle, timezone.localdate(), nummer))


@steuern
def liste(request, pk):
    """Reihenfolge des Tages als CSV (nur Kundennummern, wie die bisherige Liste)."""
    stelle = _stelle(request, pk)
    heute = timezone.localdate()
    tag = ablauf.tag_holen(stelle, heute)
    if tag is None:
        messages.info(request, "Für heute gibt es noch keine Reihenfolge.")
        return redirect("aufruf:steuerung", stelle.pk)
    antwort = HttpResponse(content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = (f'attachment; filename="reihenfolge_{heute:%Y-%m-%d}_'
                                      f'{stelle.pk}.csv"')  # fmt: skip
    antwort.write("﻿")
    w = csv.writer(antwort, delimiter=";")
    w.writerow(["Platz gesamt", "Kundengruppe", "Platz in Gruppe", "Kundennummer", "Aufgerufen",
                "Anmerkung"])  # fmt: skip
    for z in ablauf.reihenfolge(tag):
        w.writerow([z["platz"], z["gruppe"], z["gruppen_platz"], z["nummer"],
                    "ja" if z["aufgerufen"] else "", z["anmerkung"]])  # fmt: skip
    return antwort


# ── Kurz-Steuerung unter dem Menü (Ausgabestellen) ──────────────────────────


AKTIONEN = {"starten": ablauf.starten, "weiter": ablauf.weiter, "zurueck": ablauf.zurueck}


@never_cache
@steuern
def leiste(request):
    """Aufgerufene Nummern der gewählten Ausgabestelle und „Nächste hereinrufen“ (HTMX)."""
    from apps.ausgabe.stelle import aktuelle

    stelle = aktuelle(request.user)
    if stelle is not None and not AufrufEinstellungen.laden(stelle).aktiv:
        return HttpResponse("")  # an dieser Ausgabestelle wird nicht aufgerufen
    if stelle is None or not stellen_fuer(request.user).filter(pk=stelle.pk).exists():
        # Ohne gewählte Stelle nur der Weg zur ganzen Steuerung (ersetzt den Menüeintrag)
        return render(request, "aufruf/_leiste.html", {
            "ohne_stelle": True, "steuerung": reverse("aufruf:start"),
            "stelle_waehlen": rollen.hat_recht(request.user, "einlass.nutzen"),
        })  # fmt: skip
    heute = timezone.localdate()
    fehler = ""
    if request.method == "POST" and request.POST.get("aktion") in AKTIONEN:
        try:
            AKTIONEN[request.POST["aktion"]](stelle, heute)
        except ablauf.AufrufFehler as f:
            fehler = str(f)
    e = AufrufEinstellungen.laden(stelle)
    tag = ablauf.aktualisieren(stelle, heute)
    d = ablauf.stand_fuer_anzeige(tag, e, heute)
    if tag and "error" not in d and not d["finished"]:
        d["current_slot"] = tag.stand["gruppen"][tag.stand["index"]]["name"]  # ohne Uhrzeit
    return render(request, "aufruf/_leiste.html", {
        "stelle": stelle, "d": d, "anzahl": e.anzahl, "fehler": fehler,
        "gruppen_heute": "error" in d and bool(ablauf.gruppen_heute(stelle, heute)),
        "steuerung": reverse("aufruf:steuerung", args=[stelle.pk]),
    })  # fmt: skip


@require_POST
@steuern
def verschieben(request, pk, nummer):
    """Knopf am Einlass: zu spät Gekommene neu einsortieren, dann zurück zum Kunden."""
    stelle = _stelle(request, pk)
    try:
        e = ablauf.spaetzuender(stelle, timezone.localdate(), nummer)
    except ablauf.AufrufFehler as fehler:
        messages.error(request, str(fehler))
    else:
        if e["bereits"]:
            messages.info(request, f"Kunde {nummer} wurde heute bereits neu einsortiert.")
        else:
            messages.success(request, f"Kunde {nummer} wurde {e['versatz']} Plätze später "
                             f"einsortiert (neuer Platz {e['neuer_platz']}).")  # fmt: skip
    return redirect(f"{reverse('ausgabe:empfang')}?{urlencode({'nummer': nummer})}")
