"""Abholtouren (ADR 0148): die Ansicht für unterwegs (Handy) und das Planen der Touren."""

import base64
import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.adressen.forms import ImportForm
from apps.ausgabe.ampel import WOCHENTAGE
from apps.core import geheimnis, module, papierkorb
from apps.konten import rollen
from apps.touren import (
    ablauf,
    anfahrten,
    fahrten,
    heuler,
    importieren_touren,
    lieferscheine,
    suche,
    zusatz,
)
from apps.touren import start as tourstart
from apps.touren.forms import HaltForm, KurzfristigForm, NeueStationForm, TourForm
from apps.touren.models import Halt, Station, Tour, TourenEinstellungen

fahren_recht = rollen.recht_erforderlich("touren.fahren")
planen = rollen.recht_erforderlich("touren.planen")
SITZUNG_IMPORT = "touren_tourstationen_import"


def _tag(request) -> dt.date:
    try:
        return dt.date.fromisoformat(request.GET.get("tag", ""))
    except ValueError:
        return timezone.localdate()


# --- Unterwegs ----------------------------------------------------------------------------------


@never_cache
@fahren_recht
def heute(request):
    """Die Touren eines Tages; die eigenen stehen oben."""
    tag, heute_ = _tag(request), timezone.localdate()
    person = ablauf.person_von(request.user)
    zeilen = []
    for t in ablauf.touren_am(tag):
        wer = ablauf.besetzung(t, tag)
        zeilen.append({
            "tour": t, "besetzung": wer, "stationen": len(ablauf.halte(t, tag)),
            "stand": anfahrten.fortschritt(t, tag), "fahrt": fahrten.heute(t, tag),
            "darf_zusatz": zusatz.darf(request.user, t, tag),
            "meine": person is not None and any(
                b["person"] is not None and b["person"].pk == person.pk for b in wer),
        })  # fmt: skip
    zeilen.sort(key=lambda z: not z["meine"])
    return render(request, "touren/heute.html", {
        "tag": tag, "ist_heute": tag == heute_, "zeilen": zeilen,
        "davor": tag - dt.timedelta(days=1), "danach": tag + dt.timedelta(days=1),
        "eco": TourenEinstellungen.laden().eco_link,
        "darf_planen": rollen.hat_recht(request.user, "touren.planen"),
    })  # fmt: skip


@never_cache
@fahren_recht
def fahren(request, pk):
    """Eine Tour für unterwegs: Stationen der Reihe nach, je Station Navigation und Anfahrt."""
    tour = get_object_or_404(Tour.objects.select_related("fahrdienst_tour"), pk=pk)
    tag = tour.datum or _tag(request)
    gefragt = tag == timezone.localdate() and tourstart.gefragt(tour, tag)
    gestartet = tourstart.gestartet(tour, tag) if gefragt else None
    darf_start = gefragt and tourstart.darf(request.user, tour, tag)
    if darf_start and gestartet is None:
        return redirect(reverse("touren:start", args=[tour.pk]))  # erst: „Seid ihr …?“
    fahrt = fahrten.heute(tour, tag)
    fahrt_moeglich = (tag == timezone.localdate() and ablauf.faehrt_am(tour, tag)
                      and tourstart.darf(request.user, tour, tag))  # fmt: skip
    halte = ablauf.halte(tour, tag)
    # Lieferscheine sieht und füllt nur aus, wer auf dieser Tour fährt – das Büro alle (ADR 0156)
    eigene = tourstart.darf(request.user, tour, tag) or rollen.hat_recht(
        request.user, "touren.lieferscheine")  # fmt: skip
    darf_schein = (lieferscheine.an() and eigene
                   and rollen.hat_recht(request.user, "touren.lieferschein"))  # fmt: skip
    alle_scheine = lieferscheine.am_tag(tag, [h.station_id for h in halte])
    scheine = alle_scheine if eigene else {}
    da = anfahrten.am_tag(tour, tag)
    aktuell = None  # die erste Station, an der noch niemand war
    for nr, h in enumerate(halte, start=1):
        h.schein = scheine.get(h.station_id)
        h.schein_moeglich = darf_schein and h.station.lieferschein
        h.anfahrt = da.get(h.station_id)
        h.angefahren = h.anfahrt is not None or h.station_id in alle_scheine
        if aktuell is None and not h.angefahren:
            aktuell = nr
    return render(request, "touren/fahren.html", {
        "tour": tour, "tag": tag, "halte": halte, "faehrt": ablauf.faehrt_am(tour, tag),
        "besetzung": ablauf.besetzung(tour, tag),
        "routen": ablauf.routen([h.station for h in halte],
                                TourenEinstellungen.laden().start_ziel),
        "darf_planen": rollen.hat_recht(request.user, "touren.planen"),
        "gefragt": gefragt, "gestartet": gestartet, "darf_start": darf_start,
        "fahrt": fahrt, "fahrt_moeglich": fahrt_moeglich,
        "darf_zusatz": zusatz.darf(request.user, tour, tag),
        "aktuell": aktuell, "erledigt": sum(1 for h in halte if h.angefahren),
        "fahrzeuge": fahrten.fahrzeuge() if fahrt_moeglich and fahrt is None else [],
        "staende": fahrten.staende() if fahrt_moeglich and fahrt is None else {},
    })  # fmt: skip


@never_cache
@fahren_recht
def zusatzstopp(request, pk):
    """Einen Zusatzstopp für einen Tag einfügen: eine Station suchen oder eine freie Adresse
    eintragen. Für das Büro an jeder Tour des Tages, für die Mannschaft an der eigenen."""
    tour = get_object_or_404(Tour.objects.select_related("fahrdienst_tour"), pk=pk)
    tag = tour.datum or _tag(request)
    ziel = f"{reverse('touren:fahren', args=[tour.pk])}?tag={tag:%Y-%m-%d}"
    if not zusatz.darf(request.user, tour, tag):
        messages.error(request, "Sie können an dieser Tour keinen Zusatzstopp einfügen.")
        return redirect(ziel)
    neu = NeueStationForm(request.POST or None, prefix="neu")
    begriff = (request.POST.get("q") or request.GET.get("q") or "").strip()
    if request.method == "POST":
        wahl = request.POST.get("station", "")
        station = Station.objects.filter(pk=int(wahl)).first() if wahl.isdigit() else None
        fehler = ""
        if station is None and neu.ausgefuellt():
            if neu.is_valid():
                station = neu.anlegen(request.user.get_username())
            else:
                fehler = "Bitte die Adresse vollständig eintragen."
        elif station is None:
            fehler = "Bitte eine Station wählen oder eine Adresse eintragen."
        if station is not None:
            try:
                zusatz.einfuegen(tour, tag, request.user, station,
                                 request.POST.get("hinweis", ""),
                                 am_ende=request.POST.get("stelle") == "ende")  # fmt: skip
            except zusatz.ZusatzFehler as grund:
                fehler = str(grund)
            else:
                messages.success(request, f"Zusatzstopp „{station.name}“ eingefügt.")
                return redirect(ziel)
        messages.error(request, fehler)
    return render(request, "touren/zusatzstopp.html", {
        "tour": tour, "tag": tag, "neu": neu, "q": begriff, "zurueck": ziel,
        "treffer": suche.stationen(begriff, ohne_tour=None, grenze=15),
        "hinweis": request.POST.get("hinweis", ""), "mindestens": suche.MINDESTENS,
    })  # fmt: skip


@require_POST
@fahren_recht
def zusatzstopp_weg(request, pk):
    from apps.touren.models import Zusatzstopp

    stopp = get_object_or_404(Zusatzstopp.objects.select_related("tour", "station"), pk=pk)
    ziel = f"{reverse('touren:fahren', args=[stopp.tour_id])}?tag={stopp.datum:%Y-%m-%d}"
    if not zusatz.darf(request.user, stopp.tour, stopp.datum):
        messages.error(request, "Sie können diesen Zusatzstopp nicht entfernen.")
        return redirect(ziel)
    papierkorb.loeschen(request.user, "Zusatzstopp",
                        f"{stopp.station.name} ({stopp.tour}, {stopp.datum:%d.%m.%Y})", stopp,
                        recht="touren.planen")  # fmt: skip
    messages.success(request, f"Zusatzstopp „{stopp.station.name}“ entfernt.")
    return redirect(ziel)


@never_cache
@fahren_recht
def heuler_stand(request):
    """Für die Kopfzeile: der älteste neue Stopp vom Büro, den noch niemand bestätigt hat."""
    offen = heuler.offene(request.user)
    inhalt = {"stopp": offen[0] if offen else None, "weitere": max(len(offen) - 1, 0)}
    return render(request, "touren/_heuler.html", inhalt)


@require_POST
@fahren_recht
def heuler_gesehen(request, pk):
    from apps.touren.models import Zusatzstopp

    stopp = get_object_or_404(Zusatzstopp.objects.select_related("tour"), pk=pk)
    if not heuler.gesehen(stopp, request.user):
        messages.error(request, "Diesen Stopp kann nur die Mannschaft der Tour bestätigen.")
        return redirect("touren:heute")
    return redirect(f"{heuler.adresse(stopp)}#zusatz-{stopp.pk}")


@require_POST
@fahren_recht
def angefahren(request, pk, station_pk):
    """„Hier waren wir“ setzen oder zurücknehmen; danach weiter zur nächsten offenen Station."""
    tour = get_object_or_404(Tour.objects.select_related("fahrdienst_tour"), pk=pk)
    station = get_object_or_404(Station, pk=station_pk)
    try:
        if "zurueck" in request.POST:
            anfahrten.zuruecknehmen(tour, station, request.user)
        else:
            anfahrten.markieren(tour, station, request.user)
    except anfahrten.AnfahrtFehler as grund:
        messages.error(request, str(grund))
    return redirect(reverse("touren:fahren", args=[tour.pk]))


def _besetzung_aus(request) -> tuple[dict[int, int], dict[int, str]]:
    """Aus dem Formular: {Platz: pk der Person} und {Platz: Name des Gastes}."""
    wahl = {int(k[6:]): int(v) for k, v in request.POST.items()
            if k.startswith("platz_") and k[6:].isdigit() and v.isdigit()}  # fmt: skip
    gaeste = {int(k[5:]): v.strip() for k, v in request.POST.items()
              if k.startswith("gast_") and k[5:].isdigit() and v.strip()}  # fmt: skip
    return wahl, gaeste


@never_cache
@fahren_recht
def start(request, pk):
    """Vor der Tour: „Seid ihr Peter und Paul?“ – bestätigen oder die Besetzung berichtigen."""
    tour = get_object_or_404(Tour.objects.select_related("fahrdienst_tour"), pk=pk)
    tag = timezone.localdate()
    ziel = reverse("touren:fahren", args=[tour.pk])
    if not tourstart.gefragt(tour, tag):
        return redirect(ziel)
    if not tourstart.darf(request.user, tour, tag):
        messages.error(request, "Sie sind für diese Tour nicht eingetragen. Bitte im Büro melden.")
        return redirect(ziel)
    if request.method == "POST":
        wahl, gaeste = _besetzung_aus(request) if "aendern" in request.POST else ({}, {})
        try:
            geaendert = tourstart.bestaetigen(tour, tag, request.user, wahl, gaeste).geaendert
        except tourstart.StartFehler as grund:
            messages.error(request, str(grund))
            return redirect(request.path)
        messages.success(request, "Besetzung geändert und im Fahrerplan eingetragen."
                         if (wahl or gaeste) and geaendert
                         else "Besetzung bestätigt. Gute Fahrt!")  # fmt: skip
        return redirect(ziel)
    plaetze = tourstart.plaetze(tour, tag)
    return render(request, "touren/start.html", {
        "tour": tour, "tag": tag, "plaetze": plaetze, "frage": tourstart.frage(plaetze),
        "gestartet": tourstart.gestartet(tour, tag),
    })  # fmt: skip


# --- Planen -------------------------------------------------------------------------------------


@never_cache
@planen
def touren(request):
    heute_ = timezone.localdate()
    alle = list(Tour.objects.select_related("fahrdienst_tour").prefetch_related("halte"))
    return render(request, "touren/touren.html", {
        "regelmaessig": [t for t in alle if not t.datum],
        "kurzfristig": [t for t in alle if t.datum and t.datum >= heute_],
        "vergangen": [t for t in reversed(alle) if t.datum and t.datum < heute_][:20],
        "heute": heute_, "eco": TourenEinstellungen.laden().eco_link,
    })  # fmt: skip


def _form(request, tour, kurz):
    if kurz:
        start = None if tour else {"datum": _tag(request), "aktiv": True}
        return KurzfristigForm(request.POST or None, instance=tour, initial=start)
    return TourForm(request.POST or None, instance=tour, fahrdienst=module.aktiv("fahrdienst"))


@never_cache
@planen
def stationen_suche(request):
    """Treffer der Stationssuche als Baustein: zum Anhängen an eine Tour (``tour``) oder zur
    Auswahl in der Maske der kurzfristigen Tour."""
    begriff = request.GET.get("q", "").strip()
    wert = request.GET.get("tour", "")
    tour = Tour.objects.filter(pk=int(wert)).first() if wert.isdigit() else None
    grenze = 25
    return render(request, "touren/_stationen_treffer.html", {
        "treffer": suche.stationen(begriff, ohne_tour=tour, grenze=grenze), "tour": tour,
        "zu_kurz": 0 < len(begriff) < suche.MINDESTENS, "mindestens": suche.MINDESTENS,
        "grenze": grenze, "leer": not begriff,
    })  # fmt: skip


def _vorschau(stationen: list[Station]) -> dict:
    e = TourenEinstellungen.laden()
    return ablauf.vorschau(stationen, e.start_ziel, e.karten_schluessel)


@never_cache
@planen
def karte(request):
    """Routenvorschau als Baustein für die Maske der kurzfristigen Tour: die dort gewählten
    Stationen in ihrer Reihenfolge (``stationen`` mehrfach)."""
    pks = [int(p) for p in request.GET.getlist("stationen") if p.isdigit()]
    vorhanden = Station.objects.in_bulk(pks)
    gewaehlt = [vorhanden[p] for p in dict.fromkeys(pks) if p in vorhanden]
    return render(request, "touren/_karte.html", {"vorschau": _vorschau(gewaehlt)})


def _gewaehlte(request) -> list[Station]:
    """Die in der Maske gewählten Stationen in ihrer Reihenfolge (jede nur einmal)."""
    pks = [int(p) for p in request.POST.getlist("stationen") if p.isdigit()]
    vorhanden = Station.objects.in_bulk(pks)
    return [vorhanden[p] for p in dict.fromkeys(pks) if p in vorhanden]


@never_cache
@planen
def tour_neu(request):
    """Neue Tour. Eine kurzfristige Tour entsteht in einer Maske: Angaben, Stationen (gesucht
    oder gleich neu eingetragen) und auf Wunsch sofort an die Fahrer schicken."""
    kurz = "kurz" in request.GET
    form = _form(request, None, kurz)
    darf_neu = kurz and rollen.hat_recht(request.user, "touren.stationen_bearbeiten")
    neu = NeueStationForm(request.POST or None, prefix="neu") if darf_neu else None
    gewaehlt = _gewaehlte(request) if kurz and request.method == "POST" else []
    neu_ok = neu is None or not neu.ausgefuellt() or neu.is_valid()
    if request.method == "POST" and form.is_valid() and neu_ok:
        tour = form.save(commit=False)
        tour.angelegt_von = request.user.get_username()
        tour.save()
        form.save_m2m()
        if not kurz:
            messages.success(request, f"Tour „{tour}“ angelegt. Jetzt die Stationen anhängen.")
            return redirect("touren:tour", pk=tour.pk)
        if neu is not None and neu.ausgefuellt():
            gewaehlt.append(neu.anlegen(request.user.get_username()))
        for station in gewaehlt:
            ablauf.halt_anhaengen(tour, station)
        messages.success(request, f"Tour „{tour}“ mit {len(gewaehlt)} "
                         f"Station{'' if len(gewaehlt) == 1 else 'en'} angelegt.")  # fmt: skip
        if "senden" in request.POST:
            return tour_senden(request, tour.pk)
        return redirect("touren:tour", pk=tour.pk)
    return render(request, "touren/tour.html", {
        "form": form, "tour": None, "kurz": kurz, "gewaehlt": gewaehlt, "neu": neu,
        "vorschau": _vorschau(gewaehlt) if kurz else None,
        "senden": "senden" in request.POST,
    })  # fmt: skip


@never_cache
@planen
def tour(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    form = _form(request, t, t.kurzfristig)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("touren:tour", pk=t.pk)
    tag = t.datum or timezone.localdate()
    aus_plan = bool(t.fahrdienst_tour_id) and not t.datum and module.aktiv("fahrdienst")
    if aus_plan:
        tag = _tag(request) if "tag" in request.GET else _naechster_fahrtag(t)
    aenderbar = aus_plan and tourstart.aenderbar(t, tag) and tourstart.darf(request.user, t, tag)
    return render(request, "touren/tour.html", {
        "plaetze": tourstart.plaetze(t, tag) if aenderbar else [], "aenderbar": aenderbar,
        "vorschau": _vorschau([h.station for h in ablauf.halte(t) if h.station.aktiv]),
        "form": form, "tour": t, "kurz": t.kurzfristig, "halte": ablauf.halte(t),
        "halt_form": HaltForm(tour=t), "wochentage": WOCHENTAGE,
        "besetzung": ablauf.besetzung(t, tag), "tag": tag,
        "aus_fahrerplan": aus_plan, "faehrt": ablauf.faehrt_am(t, tag),
    })  # fmt: skip


def _naechster_fahrtag(tour) -> dt.date:
    """Heute, wenn die Tour heute fährt, sonst ihr nächster Fahrtag (binnen zwei Wochen)."""
    heute_ = timezone.localdate()
    for tage in range(15):
        if ablauf.faehrt_am(tour, heute_ + dt.timedelta(days=tage)):
            return heute_ + dt.timedelta(days=tage)
    return heute_


@require_POST
@planen
def besetzung_aendern(request, pk):
    """Aus der Planung: die Besetzung einer Tour aus dem Fahrerplan für einen Tag ändern
    (kurzfristiger Wechsel, Gast). Steht danach als Ersatz im Fahrerplan."""
    t = get_object_or_404(Tour.objects.select_related("fahrdienst_tour"), pk=pk)
    try:
        tag = dt.date.fromisoformat(request.POST.get("tag", ""))
    except ValueError:
        tag = timezone.localdate()
    wahl, gaeste = _besetzung_aus(request)
    try:
        if tourstart.aendern(t, tag, request.user, wahl, gaeste):
            messages.success(request, f"Besetzung am {tag:%d.%m.%Y} geändert; sie steht so "
                             "auch im Fahrerplan.")  # fmt: skip
        else:
            messages.info(request, "Nichts geändert.")
    except tourstart.StartFehler as grund:
        messages.error(request, str(grund))
    return redirect(f"{reverse('touren:tour', args=[t.pk])}?tag={tag:%Y-%m-%d}")


@require_POST
@planen
def tour_loeschen(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    papierkorb.loeschen(request.user, "Tour", str(t), t, recht="touren.planen")
    messages.success(request, f"Tour „{t}“ in den Papierkorb gelegt.")
    return redirect("touren:touren")


@require_POST
@planen
def tour_senden(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    ziel = reverse("touren:fahren", args=[t.pk])
    mit, ohne = ablauf.senden(t, request.build_absolute_uri(ziel))
    if mit:
        messages.success(request, f"Tour geschickt an: {', '.join(mit)}.")
    if ohne:
        messages.warning(request, f"Ohne E-Mail-Adresse, bitte anders Bescheid geben: "
                         f"{', '.join(ohne)}.")  # fmt: skip
    if not mit and not ohne:
        messages.error(request, "Niemand gewählt. Erst Fahrer und Beifahrer eintragen.")
    return redirect("touren:tour", pk=t.pk)


@require_POST
@planen
def halt_neu(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    form = HaltForm(request.POST, tour=t)
    if form.is_valid():
        ablauf.halt_anhaengen(t, form.cleaned_data["station"])
    else:
        messages.error(request, "Bitte eine Station wählen.")
    return redirect(reverse("touren:tour", args=[t.pk]) + "#stationen")


@require_POST
@planen
def halt_aendern(request, pk):
    """Ein Halt: früher, später, entfernen oder die Wochentage setzen."""
    h = get_object_or_404(Halt.objects.select_related("tour"), pk=pk)
    aktion = request.POST.get("aktion")
    if aktion in ("hoch", "runter"):
        ablauf.halt_bewegen(h, -1 if aktion == "hoch" else 1)
    elif aktion == "entfernen":
        h.delete()  # nur die Zuordnung; die Station bleibt
    elif aktion == "tage":
        gewaehlt = request.POST.getlist("wochentage")
        h.wochentage = ", ".join(t for t in WOCHENTAGE if t in gewaehlt)
        h.save(update_fields=["wochentage"])
    return redirect(reverse("touren:tour", args=[h.tour_id]) + "#stationen")


# --- Import der Stationsfolgen ------------------------------------------------------------------


def _bericht_aus_sitzung(request):
    gespeichert = request.session.get(SITZUNG_IMPORT)
    if not gespeichert:
        return None
    roh = geheimnis.bytes_entschluesseln(base64.b64decode(gespeichert))
    return importieren_touren.pruefen(importieren_touren.text_lesen(roh)) if roh else None


@never_cache
@planen
def touren_importieren(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    bericht = None
    if request.method == "POST" and request.POST.get("schritt") == "uebernehmen":
        try:
            bericht = _bericht_aus_sitzung(request)
        except importieren_touren.ImportFehler:
            bericht = None
        request.session.pop(SITZUNG_IMPORT, None)
        if bericht is None:
            messages.error(request, "Keine geprüfte Datei vorhanden. Bitte erneut hochladen.")
            return redirect("touren:touren_importieren")
        anzahl, halte = importieren_touren.uebernehmen(bericht, request.user.get_username())
        messages.success(request, f"{anzahl} Tour{'en' if anzahl != 1 else ''} mit {halte} "
                         "Stationen übernommen.")  # fmt: skip
        return redirect("touren:touren")
    if request.method == "POST" and form.is_valid():
        roh = form.cleaned_data["datei"].read()
        try:
            bericht = importieren_touren.pruefen(importieren_touren.text_lesen(roh))
        except importieren_touren.ImportFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("touren:touren_importieren")
        request.session[SITZUNG_IMPORT] = base64.b64encode(
            geheimnis.bytes_verschluesseln(roh)).decode()  # fmt: skip
    return render(request, "touren/touren_importieren.html", {
        "form": form, "bericht": bericht, "spalten": importieren_touren.SPALTEN,
    })  # fmt: skip
