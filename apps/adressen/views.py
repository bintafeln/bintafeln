"""Adressbuch (ADR 0044): Liste, Anlegen, Bearbeiten, Löschen, Auskunft, Import und Export."""

import base64

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError, Q, Sum
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.adressen import importieren
from apps.adressen.auskunft import adresse_pdf
from apps.adressen.forms import AdresseForm, ImportForm
from apps.adressen.models import Adresse, AdressKategorie
from apps.core import geheimnis, listen, listenauswahl, listenexport, module, papierkorb
from apps.core.pdf import pdf_antwort
from apps.konten import rollen

SITZUNG_IMPORT = "adressen_import"
HELFER = "Ehrenamtliche Helfer"  # Kategorie aus Migration 0003

# Filter „Im Verein“: (Schlüssel, Bezeichnung, nötiges Recht)
VEREIN = [
    ("mitglied", "Mitglieder (aktuell)", "mitglieder.sehen"),
    ("aktiv", "aktive Mitglieder (helfen mit)", "mitglieder.sehen"),
    ("passiv", "passive Mitglieder", "mitglieder.sehen"),
    ("helfer", "ehrenamtliche Helfer (auch aktive Mitglieder)", None),
    ("spender", "Spender", None),
]


def _verein_wahl(benutzer) -> list[tuple[str, str]]:
    return [(k, t) for k, t, recht in VEREIN if recht is None or rollen.hat_recht(benutzer, recht)]


def _im_verein(adressen, wahl: str):
    heute = timezone.localdate()
    mitglied = Q(mitglied__isnull=False) & (Q(mitglied__austritt__isnull=True)
                                            | Q(mitglied__austritt__gt=heute))  # fmt: skip
    if wahl == "mitglied":
        return adressen.filter(mitglied)
    if wahl == "aktiv":
        return adressen.filter(mitglied, mitglied__art="Aktives Mitglied")
    if wahl == "passiv":
        return adressen.filter(mitglied, mitglied__art="Nicht aktives Mitglied")
    if wahl == "helfer":
        # Mitarbeitende (Person mit Konto), die alte Kategorie „Ehrenamtliche Helfer“ oder aktive
        # Mitglieder gelten als Helfer (ADR 0097: Einteilbarkeit regelt die Rolle des Kontos).
        return adressen.filter(Q(konto__isnull=False) | Q(kategorien__name=HELFER)
                               | (mitglied & Q(mitglied__art="Aktives Mitglied")))  # fmt: skip
    if wahl == "spender":
        return adressen.filter(Q(kategorien__name="Spender") | Q(spenden__isnull=False))
    return adressen


# Schlüssel, die die Reihenfolge der Liste bestimmen (Filter + Sortierung) – ohne Blättern/Auswahl.
# Sie werden an die Adresse weitergereicht, damit man dort vor/zurück blättern kann (ADR 0097).
BLAETTER_SCHLUESSEL = ("q", "kategorie", "art", "verein", "sort")


def _gefiltert(user, params):
    """Adressbuch nach den Filtern aus ``params`` (QueryDict); ``user`` steuert die „Im Verein“.
    Ohne die je Person gemerkte Zeilenzahl – die setzt die Listen-Ansicht selbst."""
    adressen = Adresse.objects.prefetch_related("kategorien")
    q = (params.get("q") or "").strip()
    if q:
        adressen = adressen.filter(
            Q(organisation__icontains=q) | Q(vorname__icontains=q) | Q(nachname__icontains=q)
            | Q(ansprechperson__icontains=q) | Q(ort__icontains=q) | Q(plz__startswith=q)
            | Q(email__icontains=q)
        )  # fmt: skip
    kategorie = params.get("kategorie", "")
    if kategorie.isdigit():
        adressen = adressen.filter(kategorien__pk=kategorie)
    art = params.get("art", "")
    if art in Adresse.Art.values:
        adressen = adressen.filter(art=art)
    verein = params.get("verein", "")
    if verein not in dict(_verein_wahl(user)):
        verein = ""
    adressen = _im_verein(adressen, verein)
    return adressen.distinct(), {"q": q, "kategorie": kategorie, "art": art, "verein": verein}


def _blaetter_abfrage(params) -> str:
    """Nur die Filter-/Sortier-Schlüssel als Abfrage-String – Grundlage fürs Blättern und für den
    Rücksprung in die gefilterte Liste."""
    teile = QueryDict(mutable=True)
    for schluessel in BLAETTER_SCHLUESSEL:
        wert = params.get(schluessel)
        if wert:
            teile[schluessel] = wert
    return teile.urlencode()


def _reihenfolge(user, params) -> list[int]:
    """Die Adress-pks in genau der Reihenfolge der Liste (Filter + Sortierung), ohne Blättern."""
    adressen, _ = _gefiltert(user, params)
    adressen, _ = listen.sortieren(adressen, params.get("sort", ""), SORTIERUNG, "name")
    return list(adressen.values_list("pk", flat=True))


# Anzeigen: Adressen je Seite zur Wahl (Vorgabe 25), „alle“ ohne Blättern – wie in anderen Listen.
ANZAHL_WAHL = ("25", "50", "100", "alle")
JE_SEITE = 25
# Sortierbare Spalten des Adressbuchs (Schlüssel wie in ?sort=…, mit „-“ absteigend):
SORTIERUNG = {
    "name": ("organisation", "nachname", "vorname"),
    "vorname": ("vorname", "nachname"),
    "anrede": ("anrede",),
    "strasse": ("strasse",),
    "ort": ("ort", "plz"),
    "telefon": ("telefon", "mobil"),
    "email": ("email",),
}
# Zu-/abwählbare Spalten (Nachname öffnet die Adresse und steht immer, darum nicht hier) –
# getrennte Spalten wie in der Mitarbeitendenliste, standardmäßig alle sichtbar.
SPALTEN = [("vorname", "Vorname"), ("anrede", "Anrede"), ("strasse", "Straße"), ("plz", "PLZ"),
           ("ort", "Ort"), ("telefon", "Telefon"), ("mobil", "Handy"), ("email", "E-Mail"),
           ("kategorien", "Kategorien"), ("helfer", "Mitarbeit")]  # fmt: skip
SPALTEN_FEST: set = set()


@rollen.recht_erforderlich("adressen.sehen")
def liste(request):
    adressen, filter_ = _gefiltert(request.user, request.GET)
    filter_["anzahl"] = listen.zeilenzahl(request, "anzahl")  # je Person gemerkt, Vorgabe 25
    adressen, sort = listen.sortieren(adressen, request.GET.get("sort", ""), SORTIERUNG, "name")
    if request.GET.get("aktion"):
        adressen = listenauswahl.filtern(request, adressen)
        basis = f"adressen-{timezone.localdate():%Y-%m-%d}"
        return listenexport.ausliefern(request, "Adressbuch", basis,
                                       importieren.exportieren(adressen),
                                       weiter=reverse("adressen:liste"))  # fmt: skip
    je_seite = listen.je_seite(filter_["anzahl"], adressen.count(), JE_SEITE)
    seite = Paginator(
        adressen.select_related("konto").prefetch_related("konto__groups"), je_seite
    ).get_page(request.GET.get("seite"))
    abfrage = request.GET.copy()
    abfrage.pop("seite", None)
    return render(request, "adressen/liste.html", {
        "seite": seite, "filter": filter_, "anzahl": seite.paginator.count, "sort": sort,
        "anzahl_wahl": ANZAHL_WAHL,
        "kategorien": AdressKategorie.objects.all(), "arten": Adresse.Art.choices,
        "sichtbar": listen.sichtbare_spalten(request.user, "adressen",
                                             [k for k, _ in SPALTEN], SPALTEN_FEST),
        "spalten_wahl": listen.spalten_wahl(request.user, "adressen", SPALTEN, SPALTEN_FEST),
        "abfrage": abfrage.urlencode(),
        "blaetter_abfrage": _blaetter_abfrage(request.GET),
        "verein_wahl": _verein_wahl(request.user),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("adressen.sehen")
def spalten(request):
    """Speichert, welche Spalten diese Person im Adressbuch sieht, und kehrt zur Liste zurück."""
    listen.spalten_speichern(request.user, "adressen", request.POST.getlist("spalte"),
                             SPALTEN, SPALTEN_FEST)  # fmt: skip
    zurueck = QueryDict(request.POST.get("zurueck", "")).urlencode()
    ziel = reverse("adressen:liste")
    return redirect(f"{ziel}?{zurueck}" if zurueck else ziel)


@rollen.recht_erforderlich("adressen.sehen")
def adresse(request, pk):
    a = get_object_or_404(Adresse.objects.prefetch_related("kategorien"), pk=pk)
    kontext = {"a": a}
    if rollen.hat_recht(request.user, "spenden.sehen"):
        from apps.spenden.models import Spende

        spenden = a.spenden.select_related("bestaetigung")
        kontext["spenden"] = spenden[:20]
        kontext["spenden_anzahl"] = spenden.count()
        kontext["spenden_jahre"] = (
            spenden.filter(art=Spende.Art.GELD).values_list("datum__year")
            .annotate(summe=Sum("betrag")).order_by("-datum__year")
        )  # fmt: skip
    if rollen.hat_recht(request.user, "mitglieder.sehen"):
        kontext["mitglied"] = getattr(a, "mitglied", None)
        kontext["zeige_mitglied"] = True
    # Verknüpftes Konto und seine Stammdaten nur für Mitarbeitenden-Verwalter
    kontext["darf_konto"] = rollen.darf_mitarbeitende_verwalten(request.user)
    kontext["konto_rollen"] = (list(a.konto.groups.values_list("name", flat=True))
                               if a.konto_id else [])  # fmt: skip
    kontext["konto_aktiv"] = bool(a.konto_id and a.konto.is_active)
    # Regelmäßige Einsätze dieser Person (nur bei eingeschaltetem Modul, ADR 0097)
    if a.art == Adresse.Art.PERSON:
        if module.aktiv("dienstplan"):
            from apps.dienstplan import plan as dienstplan

            kontext["dienst_einsaetze"] = dienstplan.einsatztage(a)
        if module.aktiv("fahrdienst"):
            from apps.fahrdienst import plan as fahrdienst

            kontext["fahr_einsaetze"] = fahrdienst.einsatztage(a)
    # Kam man aus der Liste (Filter/Sortierung in der Abfrage), lässt sich hier vor/zurück blättern
    # und über „← Adressbuch“ in genau diese gefilterte Liste zurückspringen (ADR 0097).
    abfrage = _blaetter_abfrage(request.GET)
    kontext["zurueck"] = abfrage
    if abfrage:
        pks = _reihenfolge(request.user, request.GET)
        if a.pk in pks:
            i = pks.index(a.pk)
            kontext["blaetter_abfrage"] = abfrage
            kontext["blaetter_pos"] = (i + 1, len(pks))
            kontext["vorige"] = pks[i - 1] if i > 0 else None
            kontext["naechste"] = pks[i + 1] if i < len(pks) - 1 else None
    return render(request, "adressen/adresse.html", kontext)


@never_cache
@rollen.recht_erforderlich("adressen.bearbeiten")
def bearbeiten(request, pk=None):
    a = get_object_or_404(Adresse, pk=pk) if pk else Adresse()
    konto_waehlbar = rollen.darf_mitarbeitende_verwalten(request.user)
    form = AdresseForm(request.POST or None, instance=a, konto_waehlbar=konto_waehlbar,
                       verwalter=request.user)  # fmt: skip
    m_form, ist_mitglied = _mitglied_formular(request, a)
    gueltig = form.is_valid() and (not ist_mitglied or m_form.is_valid())
    if request.method == "POST" and gueltig:
        with transaction.atomic():
            a = form.save(commit=False)
            a.geaendert_am, a.geaendert_von = timezone.now(), request.user.get_username()
            a.save()
            form.save_m2m()
            form.rollen_anwenden()  # Rollen auf das verknüpfte Konto schreiben (ADR 0097)
            if m_form is not None and ist_mitglied:
                from apps.mitglieder.models import nummer_verbraucht

                m = m_form.save(commit=False)
                m.adresse = a
                m.save()
                nummer_verbraucht(m.nummer)
        text = f"Adresse „{a.name}“ gespeichert"
        messages.success(request, f"{text} (Mitglied {m.nummer})." if m_form is not None
                         and ist_mitglied else f"{text}.")  # fmt: skip
        return redirect("adressen:adresse", pk=a.pk)
    return render(request, "adressen/bearbeiten.html", {
        "form": form, "a": a, "m_form": m_form, "ist_mitglied": ist_mitglied,
        "schon_mitglied": m_form is not None and m_form.instance.pk is not None,
        "konto_waehlbar": konto_waehlbar,
        "konto_aktiv": bool(a.konto_id and a.konto.is_active),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("mitarbeitende.verwalten")
def konto_sperren(request, pk):
    """„Person hört auf“: sperrt das verknüpfte Konto (Archiv). Die Adresse und die Historie
    bleiben; die Kategorie „Ehemalige Ehrenamtliche“ kommt dabei automatisch dazu (ADR 0098).
    Danach ist keine Rolle mehr nötig."""
    from apps.konten import verwaltung

    a = get_object_or_404(Adresse, pk=pk)
    if a.konto_id:
        try:
            verwaltung.sperren(request.user, a.konto)
            messages.success(request, f"Konto von „{a.name}“ gesperrt. Die Person bleibt als "
                             "Adresse erhalten.")  # fmt: skip
        except verwaltung.VerwaltungsFehler as fehler:
            messages.error(request, str(fehler))
    return redirect("adressen:adresse", pk=a.pk)


@require_POST
@rollen.recht_erforderlich("mitarbeitende.verwalten")
def konto_entsperren(request, pk):
    """Nimmt die Sperre wieder zurück (Person macht doch weiter)."""
    from apps.konten import verwaltung

    a = get_object_or_404(Adresse, pk=pk)
    if a.konto_id:
        try:
            verwaltung.entsperren(request.user, a.konto)
            messages.success(request, f"Konto von „{a.name}“ ist wieder aktiv.")
        except verwaltung.VerwaltungsFehler as fehler:
            messages.error(request, str(fehler))
    return redirect("adressen:adresse", pk=a.pk)


def _mitglied_formular(request, a: Adresse):
    """Mitgliedschaft direkt bei der Adresse (Recht „Mitglieder bearbeiten“): bei Mitgliedern
    immer, sonst über das Häkchen „Ist Vereinsmitglied“. Löschen geht nur auf der Mitgliedsseite.
    Ergebnis: (Formular oder None, ob die Mitgliedsangaben gelten)."""
    if not rollen.hat_recht(request.user, "mitglieder.bearbeiten"):
        return None, False
    from apps.mitglieder.forms import MitgliedForm
    from apps.mitglieder.models import Mitglied, MitgliederEinstellungen

    m = Mitglied.objects.filter(adresse=a).first() if a.pk else None
    initial = {}
    if m is None:
        e = MitgliederEinstellungen.laden()
        m = Mitglied(eintritt=timezone.localdate(), jahresbeitrag=e.standard_beitrag)
        initial["nummer"] = e.naechste_nummer
    if m.pk:
        ist = True
    elif request.method == "POST":
        ist = request.POST.get("ist_mitglied") == "1"
    else:
        ist = request.GET.get("mitglied") == "1"  # vom „Neues Mitglied“ gekommen
    daten = request.POST if request.method == "POST" and ist else None
    return MitgliedForm(daten, instance=m, initial=initial, prefix="m", ohne_adresse=True), ist


@require_POST
@rollen.recht_erforderlich("adressen.loeschen")
def loeschen(request, pk):
    a = get_object_or_404(Adresse, pk=pk)
    name = a.name
    try:
        papierkorb.loeschen(request.user, "Adresse", name, a, recht="adressen.loeschen")
    except ProtectedError:
        messages.error(request, f"„{name}“ hat Spenden, Zuwendungsbestätigungen oder eine "
                                "Mitgliedschaft und lässt sich deshalb nicht löschen.")  # fmt: skip
        return redirect("adressen:adresse", pk=pk)
    messages.success(request, f"Adresse „{name}“ in den Papierkorb gelegt.")
    return redirect("adressen:liste")


@rollen.recht_erforderlich("adressen.sehen")
def auskunft(request, pk):
    a = get_object_or_404(Adresse, pk=pk)
    return pdf_antwort(adresse_pdf(a), f"auskunft-adresse-{a.pk}.pdf")


def _bericht_aus_sitzung(request):
    gespeichert = request.session.get(SITZUNG_IMPORT)
    if not gespeichert:
        return None
    roh = geheimnis.bytes_entschluesseln(base64.b64decode(gespeichert))
    return importieren.pruefen(importieren.text_lesen(roh)) if roh else None


@never_cache
@rollen.recht_erforderlich("adressen.importieren")
def importieren_ansicht(request):
    if request.method != "POST":
        # Ein Weg für alle Importe: der Import-Assistent (ADR 0078) kennt das Adressbuch
        return redirect(f"{reverse('datenimport:start')}?ziel=adressen")
    form = ImportForm(request.POST or None, request.FILES or None)
    bericht = None
    if request.method == "POST" and request.POST.get("schritt") == "uebernehmen":
        try:
            bericht = _bericht_aus_sitzung(request)
        except importieren.ImportFehler:
            bericht = None
        request.session.pop(SITZUNG_IMPORT, None)
        if bericht is None:
            messages.error(request, "Keine geprüfte Datei vorhanden. Bitte erneut hochladen.")
            return redirect("adressen:importieren")
        anzahl = importieren.uebernehmen(bericht, request.user.get_username())
        messages.success(request, f"{anzahl} Adresse{'n' if anzahl != 1 else ''} übernommen.")
        return redirect("adressen:liste")
    if request.method == "POST" and form.is_valid():
        roh = form.cleaned_data["datei"].read()
        try:
            bericht = importieren.pruefen(importieren.text_lesen(roh))
        except importieren.ImportFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("adressen:importieren")
        # Bis zum Übernehmen verschlüsselt in der Sitzung (Adressen sind Personendaten)
        request.session[SITZUNG_IMPORT] = base64.b64encode(
            geheimnis.bytes_verschluesseln(roh)
        ).decode()
    return render(request, "adressen/importieren.html", {
        "form": form, "bericht": bericht, "spalten": importieren.SPALTEN,
    })  # fmt: skip


DRUCK_VORGABE = ["nachname", "vorname", "telefon", "mobil", "email", "rollen"]


@rollen.recht_erforderlich("adressen.sehen")
def druckliste(request):
    """Mitarbeitende und Adressbuch-Personen zu einer Liste zusammenstellen und als PDF drucken
    (A4/A3, hoch/quer). Konto-Spalten/Filter nur mit dem Recht „mitarbeitende.verwalten“."""
    from django.contrib.auth.models import Group

    from apps.adressen import druckliste as dl
    from apps.kunden.models import Ausgabestelle

    darf_mitarbeit = rollen.hat_recht(request.user, "mitarbeitende.verwalten")
    katalog = dl.spalten_katalog(darf_mitarbeit)
    gueltig = {k for k, _ in katalog}
    if "spalte" in request.GET:
        gewaehlt = [k for k in request.GET.getlist("spalte") if k in gueltig]
    else:
        gewaehlt = [k for k in DRUCK_VORGABE if k in gueltig]
    spalten = [(k, t) for k, t in katalog if k in dl.SPALTEN_FEST or k in gewaehlt]
    f, adressen = dl.filtern(request, darf_mitarbeit)
    ids = [int(i) for i in request.GET.getlist("id") if i.isdigit()]

    if request.GET.get("aktion") == "pdf":
        auswahl = list(adressen.filter(pk__in=ids) if ids else adressen)
        format_ = "a3" if request.GET.get("format") == "a3" else "a4"
        quer = request.GET.get("ausrichtung", "quer") != "hoch"
        daten = dl.pdf("Mitarbeitende und Personen", spalten, auswahl, format_, quer)
        return pdf_antwort(daten, f"liste-{timezone.localdate():%Y-%m-%d}.pdf")

    adressen = list(adressen)
    vorschau = list(
        zip([a.pk for a in adressen], dl.zeilen(adressen, [k for k, _ in spalten]), strict=True)
    )
    return render(request, "adressen/druckliste.html", {
        "f": f, "darf_mitarbeit": darf_mitarbeit,
        "spalten_wahl": [(k, t, k in dl.SPALTEN_FEST or k in gewaehlt, k in dl.SPALTEN_FEST)
                         for k, t in katalog],
        "kopf": [t for _, t in spalten], "vorschau": vorschau, "anzahl": len(adressen),
        "rollen_wahl": (sorted(Group.objects.values_list("name", flat=True))
                        if darf_mitarbeit else []),
        "stellen": Ausgabestelle.objects.order_by("name") if darf_mitarbeit else [],
        "format": "a3" if request.GET.get("format") == "a3" else "a4",
        "ausrichtung": "hoch" if request.GET.get("ausrichtung") == "hoch" else "quer",
    })  # fmt: skip
