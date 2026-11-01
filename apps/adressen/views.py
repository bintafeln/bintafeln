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
        return adressen.filter(mitglied, mitglied__art="Passives Mitglied")
    if wahl == "helfer":
        # Mitarbeitende (Person mit Konto), die alte Kategorie „Ehrenamtliche Helfer“ oder aktive
        # Mitglieder gelten als Helfer (ADR 0097: Einteilbarkeit regelt die Rolle des Kontos).
        return adressen.filter(Q(konto__isnull=False) | Q(kategorien__name=HELFER)
                               | (mitglied & Q(mitglied__art="Aktives Mitglied")))  # fmt: skip
    if wahl == "spender":
        return adressen.filter(Q(kategorien__name="Spender") | Q(spenden__isnull=False))
    return adressen


def _gefiltert(request):
    adressen = Adresse.objects.prefetch_related("kategorien")
    q = request.GET.get("q", "").strip()
    if q:
        adressen = adressen.filter(
            Q(organisation__icontains=q) | Q(vorname__icontains=q) | Q(nachname__icontains=q)
            | Q(ansprechperson__icontains=q) | Q(ort__icontains=q) | Q(plz__startswith=q)
            | Q(email__icontains=q)
        )  # fmt: skip
    kategorie = request.GET.get("kategorie", "")
    if kategorie.isdigit():
        adressen = adressen.filter(kategorien__pk=kategorie)
    art = request.GET.get("art", "")
    if art in Adresse.Art.values:
        adressen = adressen.filter(art=art)
    verein = request.GET.get("verein", "")
    if verein not in dict(_verein_wahl(request.user)):
        verein = ""
    adressen = _im_verein(adressen, verein)
    return adressen.distinct(), {"q": q, "kategorie": kategorie, "art": art, "verein": verein}


# Sortierbare Spalten des Adressbuchs (Schlüssel wie in ?sort=…, mit „-“ absteigend):
SORTIERUNG = {
    "name": ("organisation", "nachname", "vorname"),
    "ort": ("ort", "plz"),
    "telefon": ("telefon", "mobil"),
    "email": ("email",),
}
# Spalten zum Zu-/Abwählen je Person (Name öffnet die Adresse und bleibt immer sichtbar).
SPALTEN = [("name", "Name"), ("ort", "Ort"), ("telefon", "Telefon"), ("email", "E-Mail"),
           ("kategorien", "Kategorien"), ("helfer", "Mitarbeit")]  # fmt: skip
SPALTEN_FEST = {"name"}


@rollen.recht_erforderlich("adressen.sehen")
def liste(request):
    adressen, filter_ = _gefiltert(request)
    adressen, sort = listen.sortieren(adressen, request.GET.get("sort", ""), SORTIERUNG, "name")
    if request.GET.get("aktion"):
        adressen = listenauswahl.filtern(request, adressen)
        basis = f"adressen-{timezone.localdate():%Y-%m-%d}"
        return listenexport.ausliefern(request, "Adressbuch", basis,
                                       importieren.exportieren(adressen),
                                       weiter=reverse("adressen:liste"))  # fmt: skip
    seite = Paginator(
        adressen.select_related("mitglied", "konto").prefetch_related("konto__groups"), 50
    ).get_page(request.GET.get("seite"))
    abfrage = request.GET.copy()
    abfrage.pop("seite", None)
    return render(request, "adressen/liste.html", {
        "seite": seite, "filter": filter_, "anzahl": seite.paginator.count, "sort": sort,
        "kategorien": AdressKategorie.objects.all(), "arten": Adresse.Art.choices,
        "sichtbar": listen.sichtbare_spalten(request.user, "adressen",
                                             [k for k, _ in SPALTEN], SPALTEN_FEST),
        "spalten_wahl": listen.spalten_wahl(request.user, "adressen", SPALTEN, SPALTEN_FEST),
        "abfrage": abfrage.urlencode(),
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
