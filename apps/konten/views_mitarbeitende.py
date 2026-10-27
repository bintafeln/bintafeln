"""Mitarbeitende verwalten: Liste, Archiv, anlegen, bearbeiten, sperren, zurücksetzen."""

from functools import wraps

from auditlog.signals import accessed
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django_otp import user_has_device

from apps.core import mail, papierkorb
from apps.core.pdf import pdf_antwort
from apps.konten import (
    auskunft,
    einladung,
    personal,
    rollen,
    verwaltung,
    views_dokumente,
    zwei_faktor,
)
from apps.konten.forms import (
    DokumentKategorieForm,
    MitarbeiterForm,
    PersonalEinstellungenForm,
    SchulungForm,
    StammdatenForm,
)
from apps.konten.models import DokumentKategorie, PersonalEinstellungen, Schulung, Stammdaten


def verwalter_erforderlich(ansicht):
    @wraps(ansicht)
    @login_required
    def pruefen(request, *args, **kwargs):
        if not rollen.darf_mitarbeitende_verwalten(request.user):
            raise PermissionDenied
        return ansicht(request, *args, **kwargs)

    return pruefen


def _zeilen(benutzer):
    """Konten mit Rollen (in fester Reihenfolge) und Zwei-Faktor-Stand für die Listen."""
    zeilen = []
    alle = rollen.alle_rollen()
    for b in benutzer.prefetch_related("groups").order_by("last_name", "first_name", "username"):
        namen = {g.name for g in b.groups.all()}
        zeilen.append(
            {
                "b": b,
                "rollen": [
                    r.name
                    for r in alle
                    if r.name in namen or (b.is_superuser and r.name == rollen.ADMIN)
                ],
                "zwei_faktor": user_has_device(b),
            }
        )
    return zeilen


@verwalter_erforderlich
def liste(request):
    personal.stammdaten_leeren()
    return render(
        request,
        "konten/mitarbeitende.html",
        {
            "zeilen": _zeilen(get_user_model().objects.filter(is_active=True, stelle__isnull=True)),
            "archiv": False,
            "faellig": personal.faelligkeiten(),
        },
    )


@verwalter_erforderlich
def archiv(request):
    return render(
        request,
        "konten/mitarbeitende.html",
        {
            "zeilen": _zeilen(
                get_user_model().objects.filter(is_active=False, stelle__isnull=True)
            ),
            "archiv": True,
        },
    )


def _startpasswort_zeigen(request, ziel, passwort, neu):
    # Die aufrufenden Ansichten sind never_cache: Das Passwort landet in keinem Zwischenspeicher.
    return render(
        request,
        "konten/startpasswort.html",
        {"ziel": ziel, "passwort": passwort, "neu": neu},
    )


@never_cache
@verwalter_erforderlich
def anlegen(request):
    form = MitarbeiterForm(
        request.POST or None, verwalter=request.user, mail_moeglich=mail.eingerichtet()
    )
    if request.method == "POST" and form.is_valid():
        daten = {f: form.cleaned_data[f] for f in MitarbeiterForm.Meta.fields
                 if f != "ausgabestellen"}  # fmt: skip
        per_mail = form.cleaned_data.get("zugang") == "einladung"
        # Das Formular bietet nur erlaubte Rollen an; verwaltung.anlegen prüft es trotzdem.
        ziel, passwort = verwaltung.anlegen(
            request.user, daten, form.cleaned_data["rollen"], einladung=per_mail
        )
        ziel.ausgabestellen.set(form.cleaned_data["ausgabestellen"])
        if not per_mail:
            return _startpasswort_zeigen(request, ziel, passwort, neu=True)
        try:
            einladung.senden(request, ziel, einladung.EINLADUNG)
        except mail.MailFehler as fehler:
            # Konto gibt es schon; dann eben mit Startpasswort weiter.
            passwort = verwaltung.passwort_zuruecksetzen(request.user, ziel)
            messages.error(request, f"Die Einladung konnte nicht gesendet werden: {fehler}")
            return _startpasswort_zeigen(request, ziel, passwort, neu=True)
        messages.success(request, f"{ziel} ist angelegt. Die Einladung ging an {ziel.email}.")
        return redirect("konten:mitarbeiter", pk=ziel.pk)
    return render(request, "konten/mitarbeiter.html", {"form": form, "ziel": None})


def _ziel(request, pk):
    ziel = get_object_or_404(get_user_model(), pk=pk)
    if not verwaltung.darf_bearbeiten(request.user, ziel):
        raise PermissionDenied
    return ziel


@verwalter_erforderlich
def bearbeiten(request, pk):
    ziel = _ziel(request, pk)
    if ziel.stelle_id:  # Konto einer Ausgabestelle: eigene Seite (ADR 0059)
        return redirect("konten:stelle", pk=ziel.stelle_id)
    form = MitarbeiterForm(request.POST or None, instance=ziel, verwalter=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            verwaltung.bearbeiten(request.user, form.instance, form.cleaned_data["rollen"])
        except verwaltung.VerwaltungsFehler as fehler:
            form.add_error("rollen", str(fehler))
        else:
            form.instance.ausgabestellen.set(form.cleaned_data["ausgabestellen"])
            messages.success(request, f"Änderungen an {ziel} gespeichert.")
            return redirect("konten:mitarbeitende")
    return render(
        request,
        "konten/mitarbeiter.html",
        {
            "form": form,
            "ziel": ziel,
            "zwei_faktor": user_has_device(ziel),
            "vertraute_geraete": ziel.vertraute_geraete.filter(
                gueltig_bis__gt=timezone.now()
            ).count(),
            "mail": mail.eingerichtet(),
        },
    )


def _aktion(request, pk, funktion, erfolg):
    ziel = _ziel(request, pk)
    try:
        funktion(request.user, ziel)
    except verwaltung.VerwaltungsFehler as fehler:
        messages.error(request, str(fehler))
    else:
        messages.success(request, erfolg.format(ziel=ziel))
    return redirect("konten:mitarbeiter", pk=ziel.pk)


@require_POST
@verwalter_erforderlich
def sperren(request, pk):
    return _aktion(
        request, pk, verwaltung.sperren, "{ziel} ist gesperrt und steht jetzt im Archiv."
    )


@require_POST
@verwalter_erforderlich
def entsperren(request, pk):
    return _aktion(request, pk, verwaltung.entsperren, "{ziel} ist wieder aktiv.")


@require_POST
@verwalter_erforderlich
def zwei_faktor_zuruecksetzen(request, pk):
    def zuruecksetzen(verwalter, ziel):
        zwei_faktor.abschalten(ziel)

    return _aktion(
        request,
        pk,
        zuruecksetzen,
        "Zwei-Faktor für {ziel} zurückgesetzt. Bei Pflicht muss es neu eingerichtet werden.",
    )


@require_POST
@verwalter_erforderlich
def geraete_zuruecksetzen(request, pk):
    def zuruecksetzen(verwalter, ziel):
        zwei_faktor.vertrauen_entziehen(ziel)

    return _aktion(
        request, pk, zuruecksetzen,
        "Vertraute Geräte von {ziel} entfernt: Bei der nächsten Anmeldung ist überall der Code "
        "nötig.",
    )  # fmt: skip


@require_POST
@verwalter_erforderlich
def link_senden(request, pk):
    """Schickt einen Link zum Festlegen eines neuen Passworts; das alte gilt bis dahin weiter."""
    ziel = _ziel(request, pk)
    try:
        einladung.senden(request, ziel, einladung.ZURUECKSETZEN)
    except mail.MailFehler as fehler:
        messages.error(request, f"Nicht gesendet: {fehler}")
    else:
        messages.success(request, f"Link zum Festlegen eines Passworts an {ziel.email} gesendet.")
    return redirect("konten:mitarbeiter", pk=ziel.pk)


@never_cache
@require_POST
@verwalter_erforderlich
def passwort_zuruecksetzen(request, pk):
    ziel = _ziel(request, pk)
    passwort = verwaltung.passwort_zuruecksetzen(request.user, ziel)
    return _startpasswort_zeigen(request, ziel, passwort, neu=False)


# --- Stammdaten, Führerschein-Kopie, Schulungen (ADR 0017) ---------------------------------


def _stammdaten(ziel):
    return Stammdaten.objects.get_or_create(benutzer=ziel)[0]


@verwalter_erforderlich
def stammdaten(request, pk):
    ziel = _ziel(request, pk)
    s = _stammdaten(ziel)
    form = StammdatenForm(request.POST or None, instance=s, angemeldet=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Stammdaten von {ziel} gespeichert.")
        return redirect("konten:stammdaten", pk=ziel.pk)
    return render(
        request,
        "konten/stammdaten.html",
        {
            "ziel": ziel,
            "s": s,
            "form": form,
            "schulung_form": SchulungForm(),
            "schulungen": ziel.schulungen.all(),
            "einstellungen": PersonalEinstellungen.laden(),
            **views_dokumente.kontext(request, ziel),
        },
    )


@require_POST
@verwalter_erforderlich
def kopie_hochladen(request, pk):
    ziel = _ziel(request, pk)
    datei = request.FILES.get("kopie")
    try:
        if datei is None:
            raise personal.KopieFehler("Bitte eine Datei auswählen.")
        personal.kopie_speichern(_stammdaten(ziel), datei)
    except personal.KopieFehler as fehler:
        messages.error(request, str(fehler))
    else:
        messages.success(request, "Kopie verschlüsselt gespeichert.")
    return redirect("konten:stammdaten", pk=ziel.pk)


@never_cache
@verwalter_erforderlich
def kopie_ansehen(request, pk):
    s = _stammdaten(_ziel(request, pk))
    inhalt = personal.kopie_lesen(s)
    if inhalt is None:
        raise Http404
    accessed.send(sender=Stammdaten, instance=s)  # Abruf im Änderungsprotokoll
    antwort = HttpResponse(inhalt, content_type=s.fs_kopie_typ)
    antwort["Content-Disposition"] = "inline"
    return antwort


@require_POST
@verwalter_erforderlich
def kopie_entfernen(request, pk):
    ziel = _ziel(request, pk)
    personal.kopie_loeschen(_stammdaten(ziel))
    messages.success(request, "Kopie gelöscht.")
    return redirect("konten:stammdaten", pk=ziel.pk)


@require_POST
@verwalter_erforderlich
def schulung_neu(request, pk):
    ziel = _ziel(request, pk)
    form = SchulungForm(request.POST)
    if form.is_valid():
        form.instance.benutzer = ziel
        form.save()
        messages.success(request, "Schulung eingetragen.")
    else:
        messages.error(request, "Schulung nicht eingetragen: Thema und Datum sind Pflicht.")
    return redirect("konten:stammdaten", pk=ziel.pk)


@require_POST
@verwalter_erforderlich
def schulung_loeschen(request, pk, schulung):
    ziel = _ziel(request, pk)
    s = get_object_or_404(Schulung, pk=schulung, benutzer=ziel)
    papierkorb.loeschen(request.user, "Schulung", f"{s} ({ziel})", s,
                        recht="mitarbeitende.verwalten")  # fmt: skip
    messages.success(request, "Schulung in den Papierkorb gelegt.")
    return redirect("konten:stammdaten", pk=ziel.pk)


@rollen.recht_erforderlich("einstellungen.personal")
def personal_einstellungen(request):
    form = PersonalEinstellungenForm(request.POST or None, instance=PersonalEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("konten:personal_einstellungen")
    return render(
        request,
        "konten/personal_einstellungen.html",
        {
            "form": form,
            "kategorien": DokumentKategorie.objects.all(),
            "kategorie_form": DokumentKategorieForm(),
        },
    )


# --- Auskunft nach Art. 15 DSGVO ---------------------------------------------------------


def _auskunft_antwort(ziel):
    accessed.send(sender=get_user_model(), instance=ziel)  # Abruf im Änderungsprotokoll
    return pdf_antwort(auskunft.mitarbeiter_pdf(ziel), f"auskunft-{ziel.username}.pdf")


@never_cache
@login_required
def auskunft_ansehen(request, pk):
    """Vollständige Auskunft; deshalb nur Admin und Personal (nicht das Büro)."""
    if not views_dokumente.sieht_personal(request.user):
        raise PermissionDenied
    return _auskunft_antwort(get_object_or_404(get_user_model(), pk=pk))


@never_cache
@login_required
def meine_auskunft(request):
    if request.user.stelle_id:  # Konto einer Ausgabestelle gehört keiner Person
        raise Http404
    return _auskunft_antwort(request.user)
