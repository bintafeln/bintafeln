"""Empfang: Kundennummer scannen, Ampel sehen, Abholung eintragen."""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.ausgabe import ampel, konto
from apps.ausgabe.forms import AusgabeEinstellungenForm
from apps.ausgabe.models import AusgabeEinstellungen, Buchung
from apps.konten import rollen
from apps.kunden import werte
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Haushalt,
    KundenEinstellungen,
    Zugriff,
)

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
        .prefetch_related("personen", "sperren", "ausnahmen", "abholungen__ausgabestelle")
        .get(pk=h.pk)
    )
    erwachsene, kinder = h.groesse(KundenEinstellungen.laden().kind_bis_alter, heute)
    bewertung = ampel.bewerten(h, heute, _stelle(request), einstellungen)
    abholungen = list(h.abholungen.all())
    beitrag = einstellungen.beitrag(erwachsene, kinder)
    vorschlaege, vorschlag_hinweis = konto.vorschlaege(h, heute, einstellungen, beitrag)
    guthaben = (h.kontostand or 0) > 0
    zahlweisen = [
        (wert, name)
        for wert, name in Buchung.Zahlweise.choices
        if (wert != Buchung.Zahlweise.GUTHABEN or guthaben)
        and (wert != Buchung.Zahlweise.ANSCHREIBEN or einstellungen.anschreiben_erlaubt)
    ]
    return {
        "h": h,
        "hauptperson": next((p for p in h.personen.all() if p.ist_hauptperson), None),
        "erwachsene": erwachsene,
        "kinder": kinder,
        "bewertung": bewertung,
        "beitrag": beitrag,
        "zahlweisen": zahlweisen,
        "zahlweise_vorgabe": zahlweisen[0][0],
        "vorschlaege": vorschlaege,
        "vorschlag_hinweis": vorschlag_hinweis,
        "einzahlungen_heute": h.buchungen.filter(art=Buchung.Art.EINZAHLUNG, datum=heute),
        "einstellungen": einstellungen,
        "abholungen": abholungen[:LETZTE_ABHOLUNGEN],
        "heute_erfasst": [a for a in abholungen if a.datum == heute and a.erfasst_am],
        "darf_ausnahme": rollen.hat_rolle(request.user, rollen.ADMIN, rollen.BUERO),
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
    zahlweise = request.POST.get("zahlweise") or Buchung.Zahlweise.GUTHABEN
    if zahlweise not in Buchung.Zahlweise.values:
        return _zurueck(request, h, "Nicht eingetragen: unbekannte Zahlweise.", messages.ERROR)
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
                zahlweise,
                kontext["einstellungen"],
                stelle,
                _benutzername(request.user),
            )
            Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=jetzt.date())
    except konto.KontoFehler as fehler:
        return _zurueck(request, h, f"Nicht eingetragen: {fehler}", messages.ERROR)
    text = f"Abholung eingetragen. Bar zu zahlen: {konto.euro(zahlung.bar)}"
    if zahlung.vom_konto:
        text += f" ({konto.euro(zahlung.vom_konto)} vom Konto)"
    text += f". Kontostand jetzt: {konto.euro(zahlung.kontostand)}."
    return _zurueck(request, h, text)


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def abholung_zuruecknehmen(request, pk):
    """Nimmt eine heute am Empfang eingetragene Abholung zurück (Versehen)."""
    abholung = get_object_or_404(
        Abholung, pk=pk, datum=timezone.localdate(), erfasst_am__isnull=False
    )
    h = abholung.haushalt
    with transaction.atomic():
        if hasattr(abholung, "buchung"):
            konto.zuruecknehmen(abholung.buchung)
        abholung.delete()
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


@rollen.rolle_erforderlich(rollen.ADMIN)
def einstellungen(request):
    form = AusgabeEinstellungenForm(request.POST or None, instance=AusgabeEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen der Ausgabe gespeichert.")
        return redirect("ausgabe:einstellungen")
    return render(request, "ausgabe/einstellungen.html", {"form": form})
