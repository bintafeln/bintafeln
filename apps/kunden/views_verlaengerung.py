"""Sammel-Verlängerung der Ausweise (ADR 0068); Regeln in ``apps/kunden/verlaengerung.py``."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.konten import rollen
from apps.kunden import verlaengerung
from apps.kunden.models import KundenEinstellungen, Nachricht

MONATE = [3, 6, 12, 24]


def _monate(wert, vorgabe: int) -> int:
    return int(wert) if str(wert).isdigit() and 1 <= int(wert) <= 60 else vorgabe


@never_cache
@rollen.recht_erforderlich("kunden.bearbeiten")
def verlaengern(request):
    e = KundenEinstellungen.laden()
    heute = timezone.localdate()
    daten = request.POST if request.method == "POST" else request.GET
    monate = _monate(daten.get("monate", ""), e.ausweis_gueltig_monate)
    if request.method == "POST" and request.POST.get("wieder_oeffnen"):
        wahl = request.POST["wieder_oeffnen"]
        n = verlaengerung.wieder_oeffnen(request.user, int(wahl)) if wahl.isdigit() else None
        if n:
            messages.success(request, f"Kunde {n.kundennummer} steht wieder oben zum Prüfen.")
        return redirect(f"{reverse('kunden:verlaengern')}?monate={monate}")
    if request.method == "POST":
        wahl = {k[5:]: w for k, w in request.POST.items() if k.startswith("wahl_")}
        verlaengern = {
            n: request.POST.get(f"grund_{n}", "") for n, w in wahl.items() if w == "verlaengern"
        }
        # bisherige Form (Häkchen) wird weiter verstanden
        verlaengern |= {n: "" for n in request.POST.getlist("verlaengern") if n not in verlaengern}
        ablehnen = {
            n: request.POST.get(f"grund_{n}", "") for n, w in wahl.items() if w == "ablehnen"
        }
        ablehnen |= {n: "" for n in request.POST.getlist("ablehnen") if n not in ablehnen}
        ergebnis = {p.nummer: p.ergebnis
                    for p in verlaengerung.gemeldete(request.user, heute, monate)}  # fmt: skip
        nein = {n for n, e in ergebnis.items() if e == verlaengerung.NEIN}
        ohne_grund = sorted(n for n, g in ablehnen.items()
                            if n in ergebnis and n not in nein and not g.strip())  # fmt: skip
        trotzdem_ohne_grund = sorted(n for n, g in verlaengern.items()
                                     if n in nein and not g.strip())  # fmt: skip
        v, p = verlaengerung.ausfuehren(request.user, heute, monate, verlaengern, ablehnen,
                                        an_stelle=bool(request.POST.get("an_stelle")))  # fmt: skip
        if v or p:
            text = f"{v} Ausweis{'e' if v != 1 else ''} verlängert"
            if p:
                text += f", {p} nicht verlängert"
            messages.success(request, text + ".")
        elif not ohne_grund and not trotzdem_ohne_grund:
            messages.info(request, "Nichts ausgewählt.")
        if trotzdem_ohne_grund:
            messages.error(request, "Ohne Begründung nicht verlängert (die Bedingungen sind nicht "
                                    f"erfüllt): {', '.join(trotzdem_ohne_grund)}")  # fmt: skip
        if ohne_grund:
            messages.error(request, "Ohne Begründung nicht abgelehnt (die Bedingungen sind "
                                    f"erfüllt): {', '.join(ohne_grund)}")  # fmt: skip
        return redirect(f"{reverse('kunden:verlaengern')}?monate={monate}")
    liste = verlaengerung.gemeldete(request.user, heute, monate)
    return render(request, "kunden/verlaengern.html", {
        "liste": liste,
        "monate": monate,
        "monate_auswahl": sorted({*MONATE, e.ausweis_gueltig_monate}),
        "einstellungen": e,
        "ablehnung": e.verlaengern_ablehnung,
        "pause_text": verlaengerung.pause_text(e.verlaengern_sonst_pausieren_monate),
        "pause": e.verlaengern_sonst_pausieren_monate,
        "anzahl": {k: sum(1 for p in liste if p.ergebnis == k)
                   for k in (verlaengerung.OK, verlaengerung.NEIN, verlaengerung.UNKLAR)},
        "bedingungen": verlaengerung.bedingungen_text(e),
        "regel": e.get_verlaengern_regel_display(), "regel_satz": verlaengerung.regel_satz(e),
        "erledigte": verlaengerung.erledigte(request.user),
        "aufbewahren": Nachricht.AUFBEWAHREN_TAGE,
    })  # fmt: skip
