"""Abholungen nachtragen (ADR 0091): Liste eines Ausgabetags oder einzelne Kunden."""

import datetime as dt

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.ausgabe import konto, nachtragen
from apps.ausgabe import stelle as stellen_wahl
from apps.konten import rollen
from apps.kunden import werte

darf = rollen.recht_erforderlich("einlass.nachtragen", "einlass.nachtragen_alle")


def _benutzername(user) -> str:
    return (user.get_full_name() or user.get_username())[:100]


def _auswahl(request, daten):
    """Datum und Ausgabestelle aus den Angaben; Vorgabe heute und die gewählte Stelle."""
    heute = timezone.localdate()
    try:
        datum = dt.date.fromisoformat(daten.get("datum", ""))
    except ValueError:
        datum = heute
    waehlbar = stellen_wahl.waehlbar(request.user)
    pk = daten.get("stelle", "")
    stelle = next((s for s in waehlbar if str(s.pk) == pk), None)
    if stelle is None:
        aktuelle = stellen_wahl.aktuelle(request.user)
        stelle = aktuelle if aktuelle in waehlbar else (waehlbar[0] if waehlbar else None)
    return datum, stelle, waehlbar


def _betrag(text, vorgabe):
    wert = werte.betrag(text)
    return vorgabe if wert is None else wert


@never_cache
@darf
def seite(request):
    if request.method == "POST":
        return _speichern(request)
    datum, stelle, waehlbar = _auswahl(request, request.GET)
    heute = timezone.localdate()
    fehler = ""
    try:
        nachtragen.tag_pruefen(request.user, datum)
    except nachtragen.NachtragFehler as f:
        fehler = str(f)
    zeilen = nachtragen.liste(request.user, stelle, datum) if stelle and not fehler else []
    return render(request, "ausgabe/nachtragen.html", {
        "datum": datum, "stelle": stelle, "stellen": waehlbar, "zeilen": zeilen, "fehler": fehler,
        "heute": heute, "fruehester": nachtragen.fruehester_tag(request.user, heute),
        "alle": nachtragen.alle_tage(request.user),
        "offen": sum(1 for z in zeilen if not z.schon),
    })  # fmt: skip


def _speichern(request):
    datum, stelle, _ = _auswahl(request, request.POST)
    pk = stelle.pk if stelle else ""
    zurueck = f"{reverse('ausgabe:nachtragen')}?datum={datum:%Y-%m-%d}&stelle={pk}"
    if stelle is None:
        messages.error(request, "Bitte eine Ausgabestelle wählen.")
        return redirect(zurueck)
    von = _benutzername(request.user)
    if request.POST.get("einzeln"):
        auftraege = [(request.POST.get("kundennummer", "").strip(), request.POST.get("betrag", ""),
                      False)]  # fmt: skip
    else:
        auftraege = [(n, request.POST.get(f"betrag_{n}", ""), True)
                     for n in request.POST.getlist("nummer")]  # fmt: skip
    if not auftraege or not auftraege[0][0]:
        messages.error(request, "Niemand ausgewählt.")
        return redirect(zurueck)
    eingetragen, summe, fehler = 0, konto.NULL, []
    for nummer, text, aus_liste in auftraege:
        try:
            z = nachtragen.einzeln(request.user, nummer, stelle, datum)
        except (Http404, PermissionDenied):
            fehler.append(f"{nummer}: keinen Kunden mit dieser Nummer gefunden")
            continue
        if aus_liste and z.schon:
            continue  # schon eingetragen (z. B. doppelt abgeschickt)
        try:
            betrag = _betrag(text, z.beitrag)
            nachtragen.eintragen(request.user, z, datum, stelle, betrag, von)
        except werte.UngueltigerWert:
            fehler.append(f"{nummer}: Betrag ist kein Betrag")
        except (nachtragen.NachtragFehler, konto.KontoFehler) as f:
            fehler.append(f"{nummer}: {f}")
        else:
            eingetragen += 1
            summe += betrag
    if eingetragen:
        n = f"{eingetragen} Abholung{'en' if eingetragen != 1 else ''}"
        messages.success(request, f"{n} am {datum:%d.%m.%Y} nachgetragen, zusammen "
                         f"{konto.euro(summe)} bar.")  # fmt: skip
    for f in fehler[:20]:
        messages.error(request, f"Nicht nachgetragen – {f}")
    return redirect(zurueck)
