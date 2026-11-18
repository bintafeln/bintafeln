"""Liste aller internen Anmerkungen zu Haushalten (ADR 0143): suchen, filtern, exportieren,
löschen.

Anmerkungen stehen sonst nur beim jeweiligen Haushalt. Die Liste zeigt sie über alle Kunden
hinweg, mit dem Recht „Interne Anmerkungen sehen“; Konten einer Ausgabestelle nur die ihrer
Kunden (ADR 0034). Löschen braucht wie beim Haushalt „Kundenstamm bearbeiten“ und geht über den
Papierkorb; der Haushalt gilt danach als in bintafeln geändert.
"""

import csv
import datetime as dt
import io

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import listenauswahl, listenexport, papierkorb
from apps.konten import rollen
from apps.kunden import historie, zugang
from apps.kunden.models import Ausgabestelle, Bemerkung, Haushalt, Person

JE_SEITE = 50
RECHT = "kunden.anmerkungen"
LOESCHEN = "kunden.bearbeiten"


def _datum(wert: str):
    try:
        return dt.date.fromisoformat(wert)
    except ValueError:
        return None


# Sortieren per Klick auf den Spaltenkopf (wie in den anderen Listen); Vorgabe: neueste zuerst
SORTIERUNG = {
    "datum": "datum",
    "kunde": "haushalt__kundennummer",
    "stelle": "haushalt__kundengruppe__ausgabestelle__name",
    "text": "text",
    "von": "verfasst_von",
}


def _sortiert(anmerkungen, sort: str):
    """``sort`` wie in der Adresse („kunde“ oder „-kunde“); Unbekanntes zählt als Vorgabe."""
    feld = SORTIERUNG.get(sort.lstrip("-"))
    if not feld:
        return anmerkungen.order_by("-datum", "-pk"), ""
    ab = "-" if sort.startswith("-") else ""
    return anmerkungen.order_by(f"{ab}{feld}", "-datum", "-pk"), sort


def _anmerkungen(request):
    """Die Anmerkungen nach den Filtern der Seite, neueste zuerst; dazu die gewählten Filter."""
    f = {k: request.GET.get(k, "").strip() for k in ("stelle", "von", "bis", "q")}
    haushalte = zugang.filtern(Haushalt.objects.all(), request.user)
    anmerkungen = Bemerkung.objects.filter(haushalt__in=haushalte)
    eigene = zugang.stellen(request.user)
    stellen = Ausgabestelle.objects.order_by("name")
    if eigene is not None:
        stellen = stellen.filter(pk__in=[s.pk for s in eigene])
    stelle = stellen.filter(pk=f["stelle"]).first() if f["stelle"].isdigit() else None
    if stelle:
        anmerkungen = anmerkungen.filter(haushalt__kundengruppe__ausgabestelle=stelle)
    else:
        f["stelle"] = ""
    von, bis = _datum(f["von"]), _datum(f["bis"])
    if von:
        anmerkungen = anmerkungen.filter(datum__gte=von)
    if bis:
        anmerkungen = anmerkungen.filter(datum__lte=bis)
    if f["q"]:
        namen = (Person.objects.filter(ist_hauptperson=True)
                 .filter(Q(nachname__icontains=f["q"]) | Q(vorname__icontains=f["q"]))
                 .values("haushalt"))  # fmt: skip
        anmerkungen = anmerkungen.filter(
            Q(text__icontains=f["q"]) | Q(haushalt__kundennummer__icontains=f["q"])
            | Q(verfasst_von__icontains=f["q"]) | Q(haushalt__in=namen)
        )  # fmt: skip
    anmerkungen = anmerkungen.select_related("haushalt__kundengruppe__ausgabestelle")
    anmerkungen, f["sort"] = _sortiert(anmerkungen, request.GET.get("sort", ""))
    return anmerkungen, f, stellen


def _mit_namen(anmerkungen) -> list:
    """Hängt an jede Anmerkung Name (Hauptperson) und Ausgabestelle ihres Haushalts."""
    anmerkungen = list(anmerkungen)
    namen = {}
    personen = Person.objects.filter(haushalt__in={a.haushalt_id for a in anmerkungen},
                                     ist_hauptperson=True)  # fmt: skip
    for pk, nachname, vorname in personen.values_list("haushalt", "nachname", "vorname"):
        namen[pk] = ", ".join(t for t in (nachname, vorname) if t)
    for a in anmerkungen:
        gruppe = a.haushalt.kundengruppe
        a.kunde = namen.get(a.haushalt_id, "")
        a.stelle_name = gruppe.ausgabestelle.name if gruppe and gruppe.ausgabestelle else ""
    return anmerkungen


def _csv_text(anmerkungen) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(["Datum", "Kundennummer", "Kunde", "Ausgabestelle", "Anmerkung",
                        "Verfasst von"])  # fmt: skip
    for a in anmerkungen:
        schreiber.writerow([f"{a.datum:%d.%m.%Y}", a.haushalt.kundennummer, a.kunde,
                            a.stelle_name, " ".join(a.text.split()), a.verfasst_von])  # fmt: skip
    return puffer.getvalue()


@never_cache
@rollen.recht_erforderlich(RECHT)
def liste(request):
    anmerkungen, f, stellen = _anmerkungen(request)
    if request.GET.get("aktion"):
        gewaehlt = _mit_namen(listenauswahl.filtern(request, anmerkungen))
        return listenexport.ausliefern(request, "Anmerkungen", "anmerkungen", _csv_text(gewaehlt),
                                       weiter=reverse("kunden:anmerkungen"))  # fmt: skip
    seite = Paginator(anmerkungen, JE_SEITE).get_page(request.GET.get("seite"))
    return render(request, "kunden/anmerkungen_liste.html", {
        "seite": seite, "zeilen": _mit_namen(seite.object_list), "filter": f, "stellen": stellen,
        "darf_loeschen": rollen.hat_recht(request.user, LOESCHEN),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich(LOESCHEN)
def loeschen(request):
    """Die angehakten Anmerkungen in den Papierkorb – nur die von Kunden, die das Konto sieht."""
    from apps.kunden.views_bearbeiten import _festhalten, geaendert

    ids = [int(x) for x in request.POST.getlist("id") if x.isdigit()]
    sichtbar, _, _ = _anmerkungen(request)
    anzahl = 0
    for a in sichtbar.filter(pk__in=ids):
        h = a.haushalt
        vorher = historie.schnappschuss(h)
        papierkorb.loeschen(request.user, "Anmerkung", f"{a} (Haushalt {h.kundennummer})", a,
                            recht=LOESCHEN, kundennummer=h.kundennummer)  # fmt: skip
        geaendert(h, request)
        _festhalten(h, vorher, request)
        anzahl += 1
    if anzahl:
        messages.success(request, f"{anzahl} Anmerkung{'en' if anzahl != 1 else ''} in den "
                         "Papierkorb gelegt.")  # fmt: skip
    else:
        messages.error(request, "Bitte zuerst die Anmerkungen anhaken, die gelöscht werden "
                       "sollen.")  # fmt: skip
    zurueck = request.POST.get("zurueck", "")
    if not zurueck.startswith(reverse("kunden:anmerkungen")):
        zurueck = reverse("kunden:anmerkungen")
    return redirect(zurueck)
