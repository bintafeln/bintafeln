"""Dokumente zu Haushalten (ADR 0030): nur Admin und Büro, verschlüsselt, Abruf protokolliert."""

from auditlog.signals import accessed
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import papierkorb, privatdateien
from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.forms_bearbeiten import HaushaltDokumentForm
from apps.kunden.models import HaushaltDokument, Zugriff

MAX_MB = 10


def kontext(kundennummer: str) -> dict:
    """Für das Template kunden/_dokumente.html."""
    return {
        "dokumente": HaushaltDokument.objects.filter(kundennummer=kundennummer).select_related(
            "art"
        ),
        "dokument_form": HaushaltDokumentForm(),
    }


@require_POST
@rollen.recht_erforderlich("kunden.dokumente_verwalten")
def hochladen(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    form = HaushaltDokumentForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Nicht gespeichert: Dokumentart und Datei sind Pflicht.")
        return redirect("kunden:haushalt", kundennummer=h.kundennummer)
    datei = form.cleaned_data["datei"]
    try:
        name = privatdateien.speichern(HaushaltDokument.ORDNER, datei, max_mb=MAX_MB)
    except privatdateien.DateiFehler as fehler:
        messages.error(request, str(fehler))
        return redirect("kunden:haushalt", kundennummer=h.kundennummer)
    d = form.instance
    d.kundennummer = h.kundennummer
    d.titel = d.titel.strip() or str(d.art)
    d.datei, d.typ, d.groesse = name, datei.content_type, datei.size
    d.hochgeladen_von = request.user.get_username()[:150]
    d.save()
    messages.success(
        request, f"Dokument verschlüsselt gespeichert, wird am {d.loeschen_am:%d.%m.%Y} gelöscht."
    )
    return redirect("kunden:haushalt", kundennummer=h.kundennummer)


MAX_FOTOS = 10  # Seiten je Aufnahme


@require_POST
@rollen.recht_erforderlich("kunden.dokument_foto")
def foto(request, kundennummer):
    """Foto eines Nachweises (Bescheid, Behindertenausweis …) am Einlass oder beim Haushalt
    aufnehmen – auch mehrere Seiten (ADR 0122). Jede Aufnahme wird sofort als Dokument des
    Haushalts verschlüsselt abgelegt; eine Notiz hält fest, dass etwas abgelegt wurde. Ansehen
    darf die Fotos nur, wer „Dokumente ansehen“ hat."""
    from django.urls import reverse
    from django.utils.http import url_has_allowed_host_and_scheme

    from apps.kunden.models import Dokumentart, Notiz

    h = zugang.haushalt(request.user, kundennummer)
    zurueck = request.POST.get("zurueck", "")
    if not url_has_allowed_host_and_scheme(zurueck, allowed_hosts={request.get_host()}):
        zurueck = reverse("kunden:haushalt", args=[h.kundennummer])
    art = Dokumentart.objects.filter(aktiv=True, pk=request.POST.get("art") or 0).first()
    dateien = request.FILES.getlist("fotos")
    if art is None or not dateien:
        messages.error(request, "Nicht gespeichert: Bitte die Art wählen und ein Foto aufnehmen.")
        return redirect(zurueck)
    if len(dateien) > MAX_FOTOS:
        messages.error(request, f"Höchstens {MAX_FOTOS} Seiten auf einmal.")
        return redirect(zurueck)
    namen = []
    try:
        for datei in dateien:
            namen.append((privatdateien.speichern(HaushaltDokument.ORDNER, datei, max_mb=MAX_MB),
                          datei))  # fmt: skip
    except privatdateien.DateiFehler as fehler:
        for name, _ in namen:  # nichts halb abgelegt zurücklassen
            privatdateien.loeschen(HaushaltDokument.ORDNER, name)
        messages.error(request, str(fehler))
        return redirect(zurueck)
    von = request.user.get_username()[:150]
    heute = timezone.localdate()
    # Jede Aufnahme wird sofort gespeichert; weitere Seiten desselben Nachweises zählen weiter
    bisher = HaushaltDokument.objects.filter(
        kundennummer=h.kundennummer, art=art, hochgeladen_von=von, hochgeladen_am__date=heute
    ).count()
    for nr, (name, datei) in enumerate(namen, start=bisher + 1):
        seite = f" (Seite {nr})" if nr > 1 else ""
        HaushaltDokument.objects.create(
            kundennummer=h.kundennummer, art=art, titel=f"{art}{seite}"[:200], datei=name,
            typ=datei.content_type, groesse=datei.size, hochgeladen_von=von,
        )  # fmt: skip
    gesamt = bisher + len(namen)
    seiten = "1 Seite" if gesamt == 1 else f"{gesamt} Seiten"
    anfang = f"Foto abgelegt: {art} ("
    notiz = Notiz.objects.filter(
        kundennummer=h.kundennummer, benutzer=request.user, erstellt_am__date=heute,
        text__startswith=anfang,
    ).first()  # fmt: skip
    if notiz:  # eine Notiz je Nachweis und Tag, nicht eine je Seite
        notiz.text = f"{anfang}{seiten})"
        notiz.save(update_fields=["text"])
    else:
        Notiz.objects.create(
            kundennummer=h.kundennummer,
            text=f"{anfang}{seiten})",
            verfasst_von=(request.user.get_full_name() or request.user.get_username())[:100],
            benutzer=request.user,
        )
    zurueck += (
        "&" if "?" in zurueck else "?"
    ) + "foto=1"  # Feld bleibt für die nächste Seite offen
    messages.success(request, f"{art}: {seiten} verschlüsselt beim Haushalt abgelegt.")
    return redirect(zurueck)


@never_cache
@rollen.recht_erforderlich("kunden.dokumente")
def ansehen(request, pk):
    d = get_object_or_404(HaushaltDokument, pk=pk)
    zugang.pruefen_nummer(request.user, d.kundennummer)
    inhalt = privatdateien.lesen(HaushaltDokument.ORDNER, d.datei)
    if inhalt is None:
        raise Http404
    accessed.send(sender=HaushaltDokument, instance=d)  # Abruf im Änderungsprotokoll
    Zugriff.objects.create(
        benutzer=request.user,
        benutzername=request.user.get_username(),
        kundennummer=d.kundennummer,
    )
    antwort = HttpResponse(inhalt, content_type=d.typ)
    antwort["Content-Disposition"] = "inline"
    return antwort


@require_POST
@rollen.recht_erforderlich("kunden.dokumente_verwalten")
def loeschen(request, pk):
    d = get_object_or_404(HaushaltDokument, pk=pk)
    zugang.pruefen_nummer(request.user, d.kundennummer)
    papierkorb.loeschen(request.user, "Dokument", f"{d.titel} (Haushalt {d.kundennummer})", d,
                        recht="kunden.dokumente_verwalten",
                        kundennummer=d.kundennummer)  # fmt: skip
    messages.success(request, f"Dokument „{d.titel}“ in den Papierkorb gelegt.")
    return redirect("kunden:haushalt", kundennummer=d.kundennummer)
