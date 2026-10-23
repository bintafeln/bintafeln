"""Empfang: Kundennummer scannen, Ampel sehen, Abholung eintragen."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.ausgabe import ampel
from apps.ausgabe.forms import AusgabeEinstellungenForm
from apps.ausgabe.models import AusgabeEinstellungen
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
    return {
        "h": h,
        "hauptperson": next((p for p in h.personen.all() if p.ist_hauptperson), None),
        "erwachsene": erwachsene,
        "kinder": kinder,
        "bewertung": bewertung,
        "beitrag": einstellungen.beitrag(erwachsene, kinder),
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
    jetzt = timezone.localtime()
    Abholung.objects.create(
        haushalt=h,
        datum=jetzt.date(),
        uhrzeit=jetzt.time().replace(second=0, microsecond=0),
        beitrag=kontext["beitrag"] if beitrag is None else beitrag,
        ausgabestelle=_stelle(request),
        eingetragen_von=_benutzername(request.user),
        erfasst_am=timezone.now(),
    )
    Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=jetzt.date())
    return _zurueck(request, h, "Abholung eingetragen.")


@require_POST
@rollen.rolle_erforderlich(*EMPFANG_ROLLEN)
def abholung_zuruecknehmen(request, pk):
    """Nimmt eine heute am Empfang eingetragene Abholung zurück (Versehen)."""
    abholung = get_object_or_404(
        Abholung, pk=pk, datum=timezone.localdate(), erfasst_am__isnull=False
    )
    h = abholung.haushalt
    abholung.delete()
    letzte = h.abholungen.order_by("-datum").first()
    Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=letzte.datum if letzte else None)
    return _zurueck(request, h, "Abholung zurückgenommen.")


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
