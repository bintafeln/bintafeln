"""Dokumente zu Mitarbeitenden (ADR 0017).

Zugang hat, wer die Person als Mitarbeitende verwalten darf, oder Admin und die Rolle
Personal. Dokumente in Kategorien „nur Personal“ sehen nur Admin und die Rolle Personal.
"""

from auditlog.signals import accessed
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import privatdateien
from apps.konten import rollen, verwaltung
from apps.konten.forms import DokumentForm, DokumentKategorieForm
from apps.konten.models import Dokument, DokumentKategorie


def sieht_personal(benutzer) -> bool:
    return rollen.hat_recht(benutzer, "personal.sehen")


def _ziel(request, pk):
    # Erst das Recht prüfen, dann suchen: Wer nichts darf, erfährt nicht, welche Konten es gibt.
    if not (sieht_personal(request.user) or rollen.darf_mitarbeitende_verwalten(request.user)):
        raise PermissionDenied
    ziel = get_object_or_404(get_user_model(), pk=pk)
    if sieht_personal(request.user):
        return ziel
    if rollen.darf_mitarbeitende_verwalten(request.user) and verwaltung.darf_bearbeiten(
        request.user, ziel
    ):
        return ziel
    raise PermissionDenied


def _sichtbar(benutzer, eintraege):
    return eintraege if sieht_personal(benutzer) else eintraege.filter(nur_personal=False)


def kontext(request, ziel) -> dict:
    """Für das Template konten/_dokumente.html."""
    kategorien = _sichtbar(request.user, DokumentKategorie.objects.all())
    dokumente = ziel.dokumente.select_related("kategorie")
    if not sieht_personal(request.user):
        dokumente = dokumente.filter(kategorie__nur_personal=False)
    return {
        "dokumente": dokumente,
        "dokument_form": DokumentForm(kategorien=kategorien),
        "weiter": request.get_full_path(),
    }


def _weiter(request, ziel):
    ziel_url = request.POST.get("weiter", "")
    if url_has_allowed_host_and_scheme(ziel_url, allowed_hosts={request.get_host()}):
        return redirect(ziel_url)
    return redirect("konten:stammdaten", pk=ziel.pk)


@require_POST
@login_required
def hochladen(request, pk):
    ziel = _ziel(request, pk)
    kategorien = _sichtbar(request.user, DokumentKategorie.objects.all())
    form = DokumentForm(request.POST, request.FILES, kategorien=kategorien)
    if not form.is_valid():
        messages.error(request, "Nicht gespeichert: Kategorie, Titel und Datei sind Pflicht.")
        return _weiter(request, ziel)
    datei = form.cleaned_data["datei"]
    try:
        name = privatdateien.speichern(Dokument.ORDNER, datei, max_mb=10)
    except privatdateien.DateiFehler as fehler:
        messages.error(request, str(fehler))
        return _weiter(request, ziel)
    form.instance.benutzer = ziel
    form.instance.datei, form.instance.typ = name, datei.content_type
    form.instance.hochgeladen_von = str(request.user)[:150]
    form.save()
    messages.success(request, "Dokument verschlüsselt gespeichert.")
    return _weiter(request, ziel)


def _dokument(request, pk, dokument):
    ziel = _ziel(request, pk)
    dokumente = Dokument.objects.filter(benutzer=ziel)
    if not sieht_personal(request.user):
        dokumente = dokumente.filter(kategorie__nur_personal=False)
    return ziel, get_object_or_404(dokumente, pk=dokument)


@never_cache
@login_required
def ansehen(request, pk, dokument):
    _, d = _dokument(request, pk, dokument)
    inhalt = privatdateien.lesen(Dokument.ORDNER, d.datei)
    if inhalt is None:
        raise Http404
    accessed.send(sender=Dokument, instance=d)  # Abruf im Änderungsprotokoll
    antwort = HttpResponse(inhalt, content_type=d.typ)
    antwort["Content-Disposition"] = "inline"
    return antwort


@require_POST
@login_required
def loeschen(request, pk, dokument):
    ziel, d = _dokument(request, pk, dokument)
    privatdateien.loeschen(Dokument.ORDNER, d.datei)
    d.delete()
    messages.success(request, "Dokument gelöscht.")
    return _weiter(request, ziel)


# --- Kategorien (nur Admin) ---------------------------------------------------------------


@require_POST
@rollen.recht_erforderlich("einstellungen.personal")
def kategorie_neu(request):
    form = DokumentKategorieForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, f"Kategorie „{form.instance}“ angelegt.")
    else:
        messages.error(request, "Kategorie nicht angelegt: Name fehlt oder gibt es schon.")
    return redirect("konten:personal_einstellungen")


@require_POST
@rollen.recht_erforderlich("einstellungen.personal")
def kategorie_loeschen(request, kategorie):
    k = get_object_or_404(DokumentKategorie, pk=kategorie)
    if k.dokument_set.exists():
        messages.error(request, f"„{k}“ enthält noch Dokumente und bleibt erhalten.")
    else:
        k.delete()
        messages.success(request, f"Kategorie „{k}“ gelöscht.")
    return redirect("konten:personal_einstellungen")
