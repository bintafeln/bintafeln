"""Mitarbeitende verwalten: Liste, Archiv, anlegen, bearbeiten, sperren, zurücksetzen."""

import csv
import io
from functools import wraps

from auditlog.signals import accessed
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django_otp import user_has_device

from apps.core import listen, listenexport, mail, papierkorb
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


# Zwei getrennte Listen nach Beschäftigung (Angestellte / Ehrenamtliche); ohne Filter alle.
BESCHAEFTIGUNG_TITEL = {"ehrenamtlich": "Ehrenamtliche", "fest": "Angestellte"}

# Sortierbare Spalten (Schlüssel wie in ?sort=…, „-“ = absteigend). Anschrift/Kontakt liegen in
# den Stammdaten, darum über die Verknüpfung „stammdaten__…“.
SORTIERUNG = {
    "name": ("last_name", "first_name"),
    "vorname": ("first_name", "last_name"),
    "anrede": ("stammdaten__anrede",),
    "strasse": ("stammdaten__strasse",),
    "ort": ("stammdaten__ort", "stammdaten__plz"),
    "telefon": ("stammdaten__telefon", "stammdaten__handy"),
    "email": ("email",),
    "benutzername": ("username",),
    "beschaeftigung": ("beschaeftigung",),
    "eintritt": ("stammdaten__eintritt",),
    "anmeldung": ("last_login",),
}
# Zu-/abwählbare Spalten (Nachname öffnet das Konto und steht immer; Vorname und die übrigen sind
# frei wählbar und standardmäßig alle sichtbar).
SPALTEN = [
    ("nummer", "Nummer"),
    ("vorname", "Vorname"), ("anrede", "Anrede"), ("strasse", "Straße"), ("plz", "PLZ"),
    ("ort", "Ort"), ("telefon", "Telefon"), ("handy", "Handy"), ("email", "E-Mail"),
    ("benutzername", "Benutzername"), ("rollen", "Rollen"), ("ausgabestellen", "Ausgabestellen"),
    ("beschaeftigung", "Beschäftigung"), ("eintritt", "Dabei seit"),
    ("zwei_faktor", "Zwei-Faktor"), ("anmeldung", "Letzte Anmeldung"),
]  # fmt: skip
SPALTEN_FEST: set = set()
LISTE = "mitarbeitende"


def _suchen(konten, q):
    """Nach Name oder Benutzername filtern (für die Suche in den Listen)."""
    if q:
        konten = konten.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q)
        )
    return konten


def _zeilen(konten):
    """Konten mit Rollen, Zwei-Faktor-Stand, Stammdaten und Ausgabestellen für die Listen."""
    zeilen = []
    alle = rollen.alle_rollen()
    konten = konten.select_related("stammdaten", "adresse__mitglied").prefetch_related(
        "groups", "ausgabestellen"
    )
    for b in konten:
        namen = {g.name for g in b.groups.all()}
        try:
            sd = b.stammdaten
        except Stammdaten.DoesNotExist:
            sd = Stammdaten(benutzer=b)
        zeilen.append(
            {
                "b": b,
                "sd": sd,
                "nummer": verwaltung.personennummer(b),
                "rollen": [
                    r.name
                    for r in alle
                    if r.name in namen or (b.is_superuser and r.name == rollen.ADMIN)
                ],
                "zwei_faktor": user_has_device(b),
                "stellen": ", ".join(sorted(s.name for s in b.ausgabestellen.all())),
                "dabei_seit": sd.eintritt or (b.date_joined and b.date_joined.date()),
            }
        )
    return zeilen


def _csv(zeilen, archiv) -> str:
    """Alle Felder als CSV (für Export/Druck), unabhängig von den sichtbaren Spalten."""
    puffer = io.StringIO()
    puffer.write("﻿")
    schreiber = csv.writer(puffer, delimiter=";")
    kopf = [
        "Nummer",
        "Nachname",
        "Vorname",
        "Anrede",
        "Straße",
        "PLZ",
        "Ort",
        "Telefon",
        "Handy",
        "E-Mail",
        "Benutzername",
        "Rollen",
        "Ausgabestellen",
        "Beschäftigung",
        "Dabei seit",
    ]
    if archiv:
        kopf += ["Gesperrt am", "Gesperrt von"]
    schreiber.writerow(kopf)
    for z in zeilen:
        b, sd = z["b"], z["sd"]
        reihe = [
            z["nummer"], b.last_name, b.first_name, sd.anrede, sd.strasse, sd.plz, sd.ort,
            sd.telefon, sd.handy, b.email, b.username, ", ".join(z["rollen"]), z["stellen"],
            b.get_beschaeftigung_display(),
            z["dabei_seit"].strftime("%d.%m.%Y") if z["dabei_seit"] else "",
        ]  # fmt: skip
        if archiv:
            reihe += [b.gesperrt_am.strftime("%d.%m.%Y") if b.gesperrt_am else "", b.gesperrt_von]
        schreiber.writerow(reihe)
    return puffer.getvalue()


def _nummer_wert(z):
    """Sortierwert der Spalte „Nummer“: Zahlen numerisch, nicht-numerische danach alphabetisch."""
    n = (z["nummer"] or "").strip()
    return (0, int(n), "") if n.isdigit() else (1, 0, n.lower())


def _nach_nummer(zeilen, absteigend):
    """Zeilen nach der (im Code gebildeten) Nummer sortieren; ohne Nummer immer ans Ende –
    in beiden Richtungen, wie ``nulls_last`` bei den Datenbank-Spalten."""
    zeilen.sort(key=_nummer_wert, reverse=absteigend)
    zeilen.sort(key=lambda z: not (z["nummer"] or "").strip())  # leere stabil nach hinten
    return zeilen


def _mitarbeitende_seite(request, konten, *, archiv, art=None):
    q = (request.GET.get("q") or "").strip()
    konten = _suchen(konten, q)
    roh = request.GET.get("sort", "")
    if (roh or "").lstrip("-") == "nummer":
        # Nummer steht nicht als Feld in der Datenbank (Mitglieds- oder Personalnummer), darum die
        # schon gebauten Zeilen sortieren; Name (aus der Abfrage) als stabile Zweitsortierung.
        sort = roh
        zeilen = _nach_nummer(_zeilen(konten.order_by("last_name", "first_name")),
                              roh.startswith("-"))  # fmt: skip
    else:
        konten, sort = listen.sortieren(konten, roh, SORTIERUNG, "name")
        zeilen = _zeilen(konten)
    if request.GET.get("aktion"):
        titel = "Archiv" if archiv else BESCHAEFTIGUNG_TITEL.get(art, "Team")
        basis = f"mitarbeitende-{timezone.localdate():%Y-%m-%d}"
        return listenexport.ausliefern(
            request, f"Mitarbeitende – {titel}", basis, _csv(zeilen, archiv),
            weiter=request.path,
        )  # fmt: skip
    return render(
        request,
        "konten/mitarbeitende.html",
        {
            "zeilen": zeilen,
            "archiv": archiv,
            "art": art,
            "q": q,
            "sort": sort,
            "titel": "Archiv" if archiv else BESCHAEFTIGUNG_TITEL.get(art, "Team"),
            "faellig": None if archiv else personal.faelligkeiten(),
            "sichtbar": listen.sichtbare_spalten(
                request.user, LISTE, [k for k, _ in SPALTEN], SPALTEN_FEST
            ),
            "spalten_wahl": listen.spalten_wahl(request.user, LISTE, SPALTEN, SPALTEN_FEST),
            "abfrage": request.GET.urlencode(),
        },
    )


def _liste(request, art):
    personal.stammdaten_leeren()
    konten = get_user_model().objects.filter(is_active=True, stelle__isnull=True)
    if art:
        konten = konten.filter(beschaeftigung=art)
    return _mitarbeitende_seite(request, konten, archiv=False, art=art)


@verwalter_erforderlich
def liste(request):
    return _liste(request, art=None)


@verwalter_erforderlich
def ehrenamtliche(request):
    return _liste(request, art="ehrenamtlich")


@verwalter_erforderlich
def angestellte(request):
    return _liste(request, art="fest")


@verwalter_erforderlich
def archiv(request):
    konten = get_user_model().objects.filter(is_active=False, stelle__isnull=True)
    return _mitarbeitende_seite(request, konten, archiv=True)


@require_POST
@verwalter_erforderlich
def spalten(request):
    """Speichert, welche Spalten diese Person in den Mitarbeitenden-Listen sieht; zurück zur
    Liste, auf der man war (eine der drei: Ehrenamtliche/Angestellte/Archiv)."""
    from django.utils.http import url_has_allowed_host_and_scheme

    listen.spalten_speichern(
        request.user, LISTE, request.POST.getlist("spalte"), SPALTEN, SPALTEN_FEST
    )
    herkunft = request.META.get("HTTP_REFERER", "")
    sicher = url_has_allowed_host_and_scheme(herkunft, {request.get_host()}, request.is_secure())
    if herkunft and sicher:
        return redirect(herkunft)
    return redirect("konten:mitarbeitende")


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
    # Aus einer der beiden Listen heraus die passende Beschäftigung vorbelegen.
    art = request.GET.get("art")
    initial = {"beschaeftigung": art} if art in BESCHAEFTIGUNG_TITEL else None
    form = MitarbeiterForm(
        request.POST or None,
        verwalter=request.user,
        mail_moeglich=mail.eingerichtet(),
        initial=initial,
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
            "nummer": verwaltung.personennummer(ziel),
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
def werkseinstellungen(request, pk):
    return _aktion(
        request, pk, verwaltung.werkseinstellungen,
        "{ziel} ist auf Werkseinstellungen zurückgesetzt: persönliche Ansichten wie beim Anlegen, "
        "Rollen und Rechte unverändert.",
    )  # fmt: skip


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
