"""Einlass: Kundennummer scannen, Ampel sehen, Abholung eintragen. Dazu die Kasse."""

import datetime as dt
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.ausgabe import ampel, kasse, konto
from apps.ausgabe.forms import AusgabeEinstellungenForm
from apps.ausgabe.models import AusgabeEinstellungen, Buchung
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden import werte
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Haushalt,
    KundenEinstellungen,
    Notiz,
    Zugriff,
)
from apps.kunden.views import notiz_schreiben, notizen_kontext

EMPFANG_ROLLEN = (rollen.ADMIN, rollen.BUERO, rollen.AUSGABE)
LETZTE_ABHOLUNGEN = 5
SITZUNG_STELLE = "ausgabestelle_id"


def _stelle(request):
    pk = request.session.get(SITZUNG_STELLE)
    return Ausgabestelle.objects.filter(pk=pk).first() if pk else None


def _finden(eingabe: str):
    """Kundennummer wie gescannt; Ziffern auch ohne bzw. mit führenden Nullen."""
    eingabe = eingabe.strip()
    haushalte = Haushalt.objects.select_related("kundengruppe__ausgabestelle")
    treffer = haushalte.filter(kundennummer__iexact=eingabe).first()
    if treffer is None and eingabe.isdigit():
        treffer = haushalte.filter(kundennummer__regex=rf"^0*{int(eingabe)}$").first()
    return treffer


def _benutzername(user) -> str:
    return (user.get_full_name() or user.get_username())[:100]


def _ergebnis(request, h, meldung=None):
    """Kontext für die Ampel-Karte eines Haushalts."""
    heute = timezone.localdate()
    einstellungen = AusgabeEinstellungen.laden()
    h = (
        Haushalt.objects.select_related("kundengruppe__ausgabestelle")
        .prefetch_related(
            "personen", "abholer", "sperren", "ausnahmen", "abholungen__ausgabestelle"
        )
        .get(pk=h.pk)
    )
    erwachsene, kinder = h.groesse(KundenEinstellungen.laden().kind_bis_alter, heute)
    bewertung = ampel.bewerten(h, heute, _stelle(request), einstellungen)
    abholungen = list(h.abholungen.all())
    beitrag = einstellungen.beitrag(erwachsene, kinder)
    vorschlaege, vorschlag_hinweis = konto.vorschlaege(h, heute, einstellungen, beitrag)
    return {
        "h": h,
        "hauptperson": next((p for p in h.personen.all() if p.ist_hauptperson), None),
        "personen": sorted(h.personen.all(), key=lambda p: not p.ist_hauptperson),
        "erwachsene": erwachsene,
        "kinder": kinder,
        "bewertung": bewertung,
        "beitrag": beitrag,
        "bar_vorschlag": konto.bar_vorschlag(beitrag, h.kontostand),
        "vorschlaege": vorschlaege,
        "vorschlag_hinweis": vorschlag_hinweis,
        "einzahlungen_heute": h.buchungen.filter(art=Buchung.Art.EINZAHLUNG, datum=heute),
        "einstellungen": einstellungen,
        "abholungen": abholungen[:LETZTE_ABHOLUNGEN],
        "heute_erfasst": [a for a in abholungen if a.datum == heute and a.erfasst_am],
        "darf_ausnahme": rollen.hat_rolle(request.user, rollen.ADMIN, rollen.BUERO),
        **notizen_kontext(h.kundennummer, request.user),
        "meldung": meldung,
    }


def _antworten(request, kontext):
    if request.headers.get("HX-Request"):
        return render(request, "ausgabe/_ergebnis.html", kontext)
    return render(request, "ausgabe/empfang.html", kontext)


@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def empfang(request):
    konto.buchungsfristen_anwenden()
    kontext = {
        "stelle": _stelle(request),
        "stellen": Ausgabestelle.objects.order_by("name"),
    }
    nummer = request.GET.get("nummer", "").strip()
    if nummer:
        h = _finden(nummer)
        if h is None:
            kontext["nicht_gefunden"] = nummer
        else:
            Zugriff.objects.create(
                benutzer=request.user,
                benutzername=request.user.get_username(),
                kundennummer=h.kundennummer,
            )
            kontext.update(_ergebnis(request, h))
    return _antworten(request, kontext)


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def ausgabestelle_waehlen(request):
    pk = request.POST.get("ausgabestelle", "")
    stelle = Ausgabestelle.objects.filter(pk=pk).first() if pk.isdigit() else None
    if stelle:
        request.session[SITZUNG_STELLE] = stelle.pk
    else:
        request.session.pop(SITZUNG_STELLE, None)
    return redirect("ausgabe:empfang")


def _zurueck(request, h, text, stufe=messages.SUCCESS):
    """Nach einer Aktion: HTMX bekommt die aktualisierte Karte, sonst Weiterleitung."""
    if request.headers.get("HX-Request"):
        kontext = {"stelle": _stelle(request), **_ergebnis(request, h, meldung=text)}
        return render(request, "ausgabe/_ergebnis.html", kontext)
    messages.add_message(request, stufe, text)
    return redirect(f"{reverse('ausgabe:empfang')}?nummer={h.kundennummer}")


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def abholung_eintragen(request, kundennummer):
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    kontext = _ergebnis(request, h)
    if not kontext["bewertung"].darf_abholen:
        return _zurueck(request, h, "Nicht eingetragen: Die Ampel steht auf Rot.", messages.ERROR)
    try:
        beitrag = werte.betrag(request.POST.get("beitrag", ""))
    except werte.UngueltigerWert:
        return _zurueck(request, h, "Nicht eingetragen: Beitrag ist kein Betrag.", messages.ERROR)
    beitrag = kontext["beitrag"] if beitrag is None else beitrag
    if beitrag < 0:
        return _zurueck(request, h, "Nicht eingetragen: Beitrag ist negativ.", messages.ERROR)
    try:
        bar = werte.betrag(request.POST.get("bar", ""))
    except werte.UngueltigerWert:
        return _zurueck(
            request, h, "Nicht eingetragen: Bar gezahlt ist kein Betrag.", messages.ERROR
        )
    jetzt = timezone.localtime()
    stelle = _stelle(request)
    try:
        with transaction.atomic():
            abholung = Abholung.objects.create(
                haushalt=h,
                datum=jetzt.date(),
                uhrzeit=jetzt.time().replace(second=0, microsecond=0),
                beitrag=beitrag,
                ausgabestelle=stelle,
                eingetragen_von=_benutzername(request.user),
                erfasst_am=timezone.now(),
            )
            zahlung = konto.abholung_buchen(
                abholung,
                beitrag,
                bar,
                kontext["einstellungen"],
                stelle,
                _benutzername(request.user),
            )
            Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=jetzt.date())
    except konto.KontoFehler as fehler:
        return _zurueck(request, h, f"Nicht eingetragen: {fehler}", messages.ERROR)
    teile = [f"Abholung eingetragen. Bar erhalten: {konto.euro(zahlung.bar)}"]
    if zahlung.vom_konto:
        teile.append(f"{konto.euro(zahlung.vom_konto)} aus Guthaben")
    if zahlung.angeschrieben:
        teile.append(f"{konto.euro(zahlung.angeschrieben)} angeschrieben")
    if zahlung.gutgeschrieben:
        teile.append(f"{konto.euro(zahlung.gutgeschrieben)} als Guthaben gebucht")
    text = f"{', '.join(teile)}. Kontostand jetzt: {konto.euro(zahlung.kontostand)}."
    return _zurueck(request, h, text)


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def abholung_zuruecknehmen(request, pk):
    """Nimmt eine heute am Einlass eingetragene Abholung zurück (Versehen)."""
    abholung = get_object_or_404(
        Abholung, pk=pk, datum=timezone.localdate(), erfasst_am__isnull=False
    )
    h = abholung.haushalt
    konto.abholung_zuruecknehmen(abholung)
    letzte = h.abholungen.order_by("-datum").first()
    Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=letzte.datum if letzte else None)
    h.refresh_from_db()
    return _zurueck(
        request,
        h,
        f"Abholung zurückgenommen. Kontostand jetzt: {konto.euro(h.kontostand or 0)}.",
    )


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def einzahlung(request, kundennummer):
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    try:
        betrag = werte.betrag(request.POST.get("betrag", ""))
        konto.einzahlen(
            h,
            betrag,
            _stelle(request),
            _benutzername(request.user),
            request.POST.get("bemerkung", "").strip(),
        )
    except (werte.UngueltigerWert, konto.KontoFehler):
        return _zurueck(
            request, h, "Nicht gebucht: Bitte einen Betrag größer als 0 angeben.", messages.ERROR
        )
    h.refresh_from_db()
    return _zurueck(
        request,
        h,
        f"Einzahlung von {konto.euro(betrag)} gebucht. Bar erhalten: {konto.euro(betrag)}. "
        f"Kontostand jetzt: {konto.euro(h.kontostand)}.",
    )


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def einzahlung_zuruecknehmen(request, pk):
    """Nimmt eine heute gebuchte Einzahlung zurück (Versehen)."""
    buchung = get_object_or_404(
        Buchung,
        pk=pk,
        art=Buchung.Art.EINZAHLUNG,
        datum=timezone.localdate(),
        haushalt__isnull=False,
    )
    h = buchung.haushalt
    konto.zuruecknehmen(buchung)
    h.refresh_from_db()
    return _zurueck(
        request,
        h,
        f"Einzahlung zurückgenommen. Kontostand jetzt: {konto.euro(h.kontostand or 0)}.",
    )


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def korrektur(request, kundennummer):
    """Korrekturbuchung ohne Bargeld, von der Haushaltsseite aus."""
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    try:
        betrag = werte.betrag(request.POST.get("betrag", ""))
        konto.korrigieren(
            h, betrag, request.POST.get("begruendung", ""), _benutzername(request.user)
        )
    except (werte.UngueltigerWert, konto.KontoFehler) as fehler:
        text = str(fehler) if isinstance(fehler, konto.KontoFehler) else "Kein gültiger Betrag."
        messages.error(request, f"Nicht gebucht: {text}")
    else:
        messages.success(request, "Korrektur gebucht.")
    return redirect("kunden:haushalt", kundennummer=h.kundennummer)


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def ausnahme_erteilen(request, kundennummer):
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    begruendung = request.POST.get("begruendung", "").strip()
    if not begruendung:
        return _zurueck(request, h, "Bitte eine Begründung angeben.", messages.ERROR)
    Ausnahme.objects.create(
        haushalt=h,
        datum=timezone.localdate(),
        begruendung=begruendung,
        eingetragen_von=_benutzername(request.user),
        erfasst_am=timezone.now(),
    )
    return _zurueck(request, h, "Ausnahme für heute erteilt.")


def _datum(text, muster, ersatz):
    try:
        return dt.datetime.strptime(text, muster).date()
    except (TypeError, ValueError):
        return ersatz


def _monat_verschieben(tag: dt.date, monate: int) -> dt.date:
    index = tag.year * 12 + tag.month - 1 + monate
    return dt.date(index // 12, index % 12 + 1, 1)


@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def kasse_ansehen(request):
    """Kasse nach Tag (je Ausgabestelle), Monat (je Tag) oder Jahr (je Monat), rückwirkend."""
    heute = timezone.localdate()
    ansicht = request.GET.get("ansicht", "tag")
    stellen = Ausgabestelle.objects.order_by("name")
    stelle_pk = request.GET.get("stelle", "")
    stelle = stellen.filter(pk=stelle_pk).first() if stelle_pk.isdigit() else None
    buchungen = Buchung.objects.all()
    if stelle:
        buchungen = buchungen.filter(ausgabestelle=stelle)

    if ansicht == "jahr":
        jahr = int(request.GET["jahr"]) if request.GET.get("jahr", "").isdigit() else heute.year
        jahr = min(max(jahr, 2000), 2100)
        beginn = dt.date(jahr, 1, 1)
        buchungen = buchungen.filter(datum__year=jahr)
        zeilen = kasse.nach_monat(buchungen)
        titel = f"Jahr {jahr}"
        zurueck, vor, aktuell = {"jahr": jahr - 1}, {"jahr": jahr + 1}, {"jahr": jahr}
    elif ansicht == "monat":
        beginn = _datum(request.GET.get("monat"), "%Y-%m", heute).replace(day=1)
        buchungen = buchungen.filter(datum__year=beginn.year, datum__month=beginn.month)
        zeilen = kasse.nach_tag(buchungen)
        titel = f"{konto.MONATE[beginn.month - 1]} {beginn.year}"
        zurueck = {"monat": f"{_monat_verschieben(beginn, -1):%Y-%m}"}
        vor = {"monat": f"{_monat_verschieben(beginn, 1):%Y-%m}"}
        aktuell = {"monat": f"{beginn:%Y-%m}"}
    else:
        ansicht = "tag"
        beginn = _datum(request.GET.get("datum"), "%Y-%m-%d", heute)
        buchungen = buchungen.filter(datum=beginn)
        zeilen = kasse.nach_ausgabestelle(buchungen)
        titel = f"{ampel.WOCHENTAGE[beginn.weekday()]} {beginn:%d.%m.%Y}"
        zurueck = {"datum": f"{beginn - dt.timedelta(days=1):%Y-%m-%d}"}
        vor = {"datum": f"{beginn + dt.timedelta(days=1):%Y-%m-%d}"}
        aktuell = {"datum": f"{beginn:%Y-%m-%d}"}

    buero = rollen.hat_rolle(request.user, rollen.ADMIN, rollen.BUERO)
    filter_stelle = {"stelle": stelle.pk} if stelle else {}

    def zeile(z):
        """Titel der Zeile und gegebenenfalls Link auf die feinere Ansicht."""
        g = z["gruppe"]
        if ansicht == "jahr":
            titel = konto.MONATE[g.month - 1]
            link = urlencode({"ansicht": "monat", "monat": f"{g:%Y-%m}", **filter_stelle})
        elif ansicht == "monat":
            titel, link = (
                f"{ampel.WOCHENTAGE[g.weekday()]} {g:%d.%m.}",
                urlencode({"ansicht": "tag", "datum": f"{g:%Y-%m-%d}", **filter_stelle}),
            )
        else:
            titel, link = g or "ohne Ausgabestelle", None
        return {"titel": titel, "link": link, "werte": werte(z)}

    def werte(z):
        """(Bezeichnung, Wert, ist Betrag) je Spalte."""
        return [(name, z[k], k != "abholungen") for k, name in kasse.SPALTEN]

    summe = kasse.summe(buchungen)
    # Einzelbuchungen mit Kundennummer nur für Admin und Büro, nur in der Tagesansicht.
    einzelbuchungen = (
        buchungen.select_related("ausgabestelle").order_by("zeitpunkt")
        if buero and ansicht == "tag"
        else None
    )
    if request.GET.get("format") == "pdf":
        inhalt = kasse.bericht_pdf(
            ansicht, titel, stelle, [zeile(z) for z in zeilen], werte(summe), einzelbuchungen
        )
        return pdf_antwort(inhalt, f"kasse-{ansicht}-{beginn:%Y-%m-%d}.pdf")
    return render(
        request,
        "ausgabe/kasse.html",
        {
            "ansicht": ansicht,
            "titel": titel,
            "beginn": beginn,
            "zeilen": [zeile(z) for z in zeilen],
            "summe": werte(summe),
            "bar_gesamt": summe["bar_gesamt"],
            "spalten": kasse.SPALTEN,
            "stellen": stellen,
            "stelle": stelle,
            "zurueck": urlencode({"ansicht": ansicht, **zurueck, **filter_stelle}),
            "vor": urlencode({"ansicht": ansicht, **vor, **filter_stelle}),
            "einzelbuchungen": einzelbuchungen,
            "pdf": urlencode({"ansicht": ansicht, **aktuell, **filter_stelle, "format": "pdf"}),
        },
    )


@rollen.rolle_erforderlich(rollen.ADMIN)
def einstellungen(request):
    form = AusgabeEinstellungenForm(request.POST or None, instance=AusgabeEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen der Ausgabe gespeichert.")
        return redirect("ausgabe:einstellungen")
    return render(request, "ausgabe/einstellungen.html", {"form": form})


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def notiz(request, kundennummer):
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    if notiz_schreiben(h, request.POST.get("text", ""), request.user) is None:
        return _zurueck(request, h, "Bitte einen Text für die Notiz eingeben.", messages.ERROR)
    return _zurueck(request, h, "Notiz gespeichert.")


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def notiz_loeschen(request, pk):
    notiz = get_object_or_404(Notiz, pk=pk)
    h = get_object_or_404(Haushalt, kundennummer=notiz.kundennummer)
    if not notiz.darf_loeschen(request.user):
        return _zurueck(
            request, h, "Diese Notiz dürfen nur Büro und Admin löschen.", messages.ERROR
        )
    notiz.delete()
    return _zurueck(request, h, "Notiz gelöscht.")
