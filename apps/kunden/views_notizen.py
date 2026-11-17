"""Liste aller Notizen zu Kunden (ADR 0143): suchen, filtern, exportieren und löschen.

Notizen stehen sonst nur beim jeweiligen Haushalt. Die Liste zeigt sie über alle Kunden hinweg –
mit dem Recht „Alle Notizen löschen“; für Konten einer Ausgabestelle nur die der eigenen Kunden
(ADR 0034). Löschen geht wie beim Haushalt über den Papierkorb.
"""

import csv
import datetime as dt
import io

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import listenauswahl, listenexport, papierkorb
from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import Ausgabestelle, Haushalt, Notiz, Person

JE_SEITE = 50
# Wer alle Notizen löschen darf, darf sie auch alle sehen; am Einlass bleibt es bei den Notizen
# des einzelnen Kunden (ADR 0026).
RECHT = "kunden.notizen_loeschen"
ARTEN = [
    ("", "alle Notizen"),
    ("an_stelle", "an die Ausgabestelle gerichtet"),
    ("ungelesen", "an die Ausgabestelle, noch nicht gelesen"),
    ("abwesend", "Krankmeldungen und Abwesenheiten"),
    ("einfach", "nur einfache Notizen"),
]


def _datum(wert: str):
    try:
        return dt.date.fromisoformat(wert)
    except ValueError:
        return None


def _notizen(request):
    """Die Notizen nach den Filtern der Seite, neueste zuerst; dazu die gewählten Filter."""
    f = {k: request.GET.get(k, "").strip() for k in ("art", "stelle", "von", "bis", "q")}
    notizen = Notiz.objects.all()
    eigene = zugang.stellen(request.user)
    stellen = Ausgabestelle.objects.order_by("name")
    if eigene is not None:  # Konto einer Ausgabestelle: nur die Notizen der eigenen Kunden
        stellen = stellen.filter(pk__in=[s.pk for s in eigene])
        nummern = zugang.filtern(Haushalt.objects.all(), request.user).values("kundennummer")
        notizen = notizen.filter(kundennummer__in=nummern)
    if f["art"] == "an_stelle":
        notizen = notizen.filter(an_stelle=True)
    elif f["art"] == "ungelesen":
        notizen = notizen.filter(an_stelle=True, gelesen_am__isnull=True)
    elif f["art"] == "abwesend":
        notizen = notizen.filter(krank_von__isnull=False)
    elif f["art"] == "einfach":
        notizen = notizen.filter(an_stelle=False, krank_von__isnull=True)
    else:
        f["art"] = ""
    stelle = stellen.filter(pk=f["stelle"]).first() if f["stelle"].isdigit() else None
    if stelle:
        nummern = Haushalt.objects.filter(kundengruppe__ausgabestelle=stelle).values("kundennummer")
        notizen = notizen.filter(Q(kundennummer__in=nummern) | Q(fuer_stelle=stelle))
    else:
        f["stelle"] = ""
    von, bis = _datum(f["von"]), _datum(f["bis"])
    if von:
        notizen = notizen.filter(erstellt_am__date__gte=von)
    if bis:
        notizen = notizen.filter(erstellt_am__date__lte=bis)
    if f["q"]:
        namen = (Person.objects.filter(ist_hauptperson=True)
                 .filter(Q(nachname__icontains=f["q"]) | Q(vorname__icontains=f["q"]))
                 .values("haushalt__kundennummer"))  # fmt: skip
        notizen = notizen.filter(
            Q(text__icontains=f["q"]) | Q(kundennummer__icontains=f["q"])
            | Q(verfasst_von__icontains=f["q"]) | Q(kundennummer__in=namen)
        )  # fmt: skip
    return notizen.order_by("-erstellt_am", "-pk"), f, stellen


def _mit_haushalt(notizen) -> list:
    """Hängt an jede Notiz Name (Hauptperson) und Ausgabestelle ihres Haushalts."""
    notizen = list(notizen)
    nummern = {n.kundennummer for n in notizen}
    stelle = dict(Haushalt.objects.filter(kundennummer__in=nummern)
                  .values_list("kundennummer", "kundengruppe__ausgabestelle__name"))  # fmt: skip
    namen = {}
    personen = Person.objects.filter(haushalt__kundennummer__in=nummern, ist_hauptperson=True)
    for knr, nachname, vorname in personen.values_list(
        "haushalt__kundennummer", "nachname", "vorname"
    ):
        namen[knr] = ", ".join(t for t in (nachname, vorname) if t)
    for n in notizen:
        n.kunde = namen.get(n.kundennummer, "")
        n.stelle_name = stelle.get(n.kundennummer) or ""
        n.gibt_haushalt = n.kundennummer in stelle
    return notizen


def _art(n) -> str:
    if n.krank_von:
        bis = f" bis {n.krank_bis:%d.%m.%Y}" if n.krank_bis else ""
        return f"{n.abwesenheit_titel} {n.krank_von:%d.%m.%Y}{bis}"
    if n.an_stelle:
        gelesen = (f"gelesen {timezone.localtime(n.gelesen_am):%d.%m.%Y}"
                   if n.gelesen_am else "noch nicht gelesen")  # fmt: skip
        return f"an die Ausgabestelle, {gelesen}"
    return "Notiz"


def _csv_text(notizen) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(["Geschrieben am", "Kundennummer", "Kunde", "Ausgabestelle", "Art",
                        "Notiz", "Verfasst von"])  # fmt: skip
    for n in notizen:
        schreiber.writerow([f"{timezone.localtime(n.erstellt_am):%d.%m.%Y %H:%M}",
                            n.kundennummer, n.kunde, n.stelle_name, _art(n),
                            " ".join(n.text.split()), n.verfasst_von])  # fmt: skip
    return puffer.getvalue()


@never_cache
@rollen.recht_erforderlich(RECHT)
def liste(request):
    notizen, f, stellen = _notizen(request)
    if request.GET.get("aktion"):
        gewaehlt = _mit_haushalt(listenauswahl.filtern(request, notizen))
        return listenexport.ausliefern(request, "Notizen", "notizen", _csv_text(gewaehlt),
                                       weiter=reverse("kunden:notizen"))  # fmt: skip
    seite = Paginator(notizen, JE_SEITE).get_page(request.GET.get("seite"))
    zeilen = _mit_haushalt(seite.object_list)
    for n in zeilen:
        n.loeschbar = n.darf_loeschen(request.user)
        n.art_text = _art(n)
    return render(request, "kunden/notizen_liste.html", {
        "seite": seite, "zeilen": zeilen, "filter": f, "arten": ARTEN, "stellen": stellen,
        "darf_loeschen": any(n.loeschbar for n in zeilen),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich(RECHT)
def loeschen(request):
    """Die angehakten Notizen in den Papierkorb – nur die, die das Konto sehen und löschen darf."""
    ids = [int(x) for x in request.POST.getlist("id") if x.isdigit()]
    sichtbar, _, _ = _notizen(request)
    geloescht = uebersprungen = 0
    for n in sichtbar.filter(pk__in=ids):
        if not n.darf_loeschen(request.user):
            uebersprungen += 1
            continue
        papierkorb.loeschen(request.user, "Notiz", f"{n.text[:60]} (Haushalt {n.kundennummer})",
                            n, recht="kunden.notizen_loeschen", kundennummer=n.kundennummer,
                            still=True)  # fmt: skip
        geloescht += 1
    if not ids:
        messages.error(request, "Bitte zuerst die Notizen anhaken, die gelöscht werden sollen.")
    elif geloescht:
        messages.success(request, f"{geloescht} Notiz{'en' if geloescht != 1 else ''} in den "
                         "Papierkorb gelegt.")  # fmt: skip
    if uebersprungen:
        messages.warning(request, f"{uebersprungen} Notiz{'en' if uebersprungen != 1 else ''} "
                         "nicht gelöscht: Fremde Notizen darf nur löschen, wer das Recht „Alle "
                         "Notizen löschen“ hat.")  # fmt: skip
    zurueck = request.POST.get("zurueck", "")
    if not zurueck.startswith(reverse("kunden:notizen")):
        zurueck = reverse("kunden:notizen")
    return redirect(zurueck)
