"""Anträge bearbeiten (Admin, Büro) und das Formular einstellen (Admin)."""

import csv

from auditlog.signals import accessed
from django.contrib import messages
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.antraege import auskunft, sprachen
from apps.antraege.forms import EinstellungenForm, TextForm
from apps.antraege.models import (
    ANHANG_ORDNER,
    Antrag,
    AntragAnhang,
    AntragAnmerkung,
    AntragEinstellungen,
    AntragText,
    loeschen,
)
from apps.core import privatdateien
from apps.core.pdf import pdf_antwort
from apps.konten import rollen

bearbeiter = rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)

ANSICHTEN = {
    "offen": ("Offen", Q(status__in=Antrag.OFFEN, papierkorb_am__isnull=True)),
    "abgeschlossen": ("Abgeschlossen", Q(papierkorb_am__isnull=True) & ~Q(status__in=Antrag.OFFEN)),
    "papierkorb": ("Papierkorb", Q(papierkorb_am__isnull=False)),
}


def _gefiltert(request):
    ansicht = request.GET.get("ansicht", "offen")
    if ansicht not in ANSICHTEN:
        ansicht = "offen"
    antraege = Antrag.objects.filter(ANSICHTEN[ansicht][1])
    suche = request.GET.get("suche", "").strip()
    if suche:
        teile = Q(vorname__icontains=suche) | Q(nachname__icontains=suche)
        teile |= Q(kundennummer__iexact=suche) | Q(email__iexact=suche)
        if "-" in suche and suche.rsplit("-", 1)[1].isdigit():
            teile |= Q(pk=int(suche.rsplit("-", 1)[1]))
        antraege = antraege.filter(teile)
    return ansicht, suche, antraege


@bearbeiter
def liste(request):
    ansicht, suche, antraege = _gefiltert(request)
    return render(
        request,
        "antraege/liste.html",
        {
            "antraege": antraege.prefetch_related("personen"),
            "ansicht": ansicht,
            "ansichten": [(k, name) for k, (name, _) in ANSICHTEN.items()],
            "suche": suche,
            "offen_gesamt": Antrag.objects.filter(ANSICHTEN["offen"][1]).count(),
        },
    )


@bearbeiter
def antrag(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    accessed.send(sender=Antrag, instance=a)  # Aufruf im Änderungsprotokoll
    davor = Antrag.objects.filter(ANSICHTEN["offen"][1], eingegangen_am__lt=a.eingegangen_am)
    return render(
        request,
        "antraege/antrag.html",
        {
            "a": a,
            "sprache": sprachen.sprache(a.sprache),
            "platz": davor.count() + 1 if a.status in Antrag.OFFEN else None,
            "status_auswahl": Antrag.Status.choices,
        },
    )


@require_POST
@bearbeiter
def status(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    neu = request.POST.get("status")
    if neu in Antrag.Status.values:
        a.status_setzen(neu, request.user.get_username())
        messages.success(request, f"Status: {a.get_status_display()}.")
    return redirect("antraege:antrag", pk=a.pk)


@require_POST
@bearbeiter
def anmerkung(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    text = request.POST.get("text", "").strip()
    if text:
        AntragAnmerkung.objects.create(antrag=a, text=text, von=request.user.get_username())
        messages.success(request, "Anmerkung gespeichert.")
    return redirect("antraege:antrag", pk=a.pk)


@require_POST
@bearbeiter
def papierkorb(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    a.papierkorb_am = None if a.papierkorb_am else timezone.now()
    a.bearbeitet_von = request.user.get_username()
    a.save()
    if a.papierkorb_am:
        messages.success(request, "In den Papierkorb gelegt.")
    else:
        messages.success(request, "Aus dem Papierkorb geholt.")
    return redirect("antraege:antrag", pk=a.pk)


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN)
def endgueltig_loeschen(request, pk):
    a = get_object_or_404(Antrag, pk=pk, papierkorb_am__isnull=False)
    nummer = a.nummer
    loeschen(a)
    messages.success(request, f"Antrag {nummer} endgültig gelöscht.")
    return redirect(f"{reverse('antraege:liste')}?ansicht=papierkorb")


@never_cache
@bearbeiter
def anhang(request, pk, anhang):
    d = get_object_or_404(AntragAnhang, pk=anhang, antrag_id=pk)
    inhalt = privatdateien.lesen(ANHANG_ORDNER, d.datei)
    if inhalt is None:
        raise Http404
    accessed.send(sender=AntragAnhang, instance=d)
    antwort = HttpResponse(inhalt, content_type=d.typ)
    antwort["Content-Disposition"] = "inline"
    return antwort


@never_cache
@bearbeiter
def auskunft_pdf(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    accessed.send(sender=Antrag, instance=a)
    return pdf_antwort(auskunft.antrag_pdf(a), f"auskunft-antrag-{a.nummer}.pdf")


EXPORT_SPALTEN = [
    "nummer", "eingegangen_am", "art", "status", "sprache", "kundennummer", "anrede", "vorname",
    "nachname", "geburtsdatum", "strasse", "plz", "ort", "telefon", "email", "familienstand",
    "staatsangehoerigkeit", "wochentage", "ausgabestelle", "personen", "nachricht",
]  # fmt: skip


def _wert(a, spalte):
    if spalte == "nummer":
        return a.nummer
    if spalte == "eingegangen_am":
        return f"{timezone.localtime(a.eingegangen_am):%Y-%m-%d %H:%M}"
    if spalte == "geburtsdatum":
        return f"{a.geburtsdatum:%Y-%m-%d}" if a.geburtsdatum else ""
    if spalte == "personen":
        return " | ".join(
            f"{p.vorname} {p.nachname} {p.geburtsdatum:%Y-%m-%d}".strip()
            if p.geburtsdatum
            else f"{p.vorname} {p.nachname}".strip()
            for p in a.personen.all()
        )
    return getattr(a, spalte)


@never_cache
@bearbeiter
def export(request):
    """CSV der angezeigten Anträge in Eingangsreihenfolge, z. B. für die Warteliste."""
    ansicht, _, antraege = _gefiltert(request)
    antwort = HttpResponse(content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = (
        f'attachment; filename="antraege-{ansicht}-{timezone.localdate():%Y-%m-%d}.csv"'
    )
    antwort.write("﻿")  # damit Tabellenprogramme die Umlaute richtig lesen
    schreiber = csv.writer(antwort, delimiter=";")
    schreiber.writerow(EXPORT_SPALTEN)
    for a in antraege.prefetch_related("personen"):
        schreiber.writerow([_wert(a, name) for name in EXPORT_SPALTEN])
    return antwort


# --- Einstellungen (Admin) ---------------------------------------------------------------


@rollen.rolle_erforderlich(rollen.ADMIN)
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=AntragEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen der Anträge gespeichert.")
        return redirect("antraege:einstellungen")
    eigene = {t.sprache for t in AntragText.objects.exclude(einleitung="", bestaetigung="")}
    return render(
        request,
        "antraege/einstellungen.html",
        {
            "form": form,
            "sprachen": [(s, s.code in eigene) for s in sprachen.SPRACHEN],
        },
    )


@rollen.rolle_erforderlich(rollen.ADMIN)
def texte(request, sprache):
    if sprache not in sprachen.NACH_CODE:
        raise Http404
    instanz = AntragText.objects.filter(sprache=sprache).first() or AntragText(sprache=sprache)
    form = TextForm(request.POST or None, instance=instanz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Texte gespeichert.")
        return redirect("antraege:einstellungen")
    return render(
        request,
        "antraege/texte.html",
        {"form": form, "s": sprachen.sprache(sprache), "t": sprachen.texte(sprache)},
    )
