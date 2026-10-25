"""Kundenstamm bearbeiten (ADR 0025; Rechte nach ADR 0033).

Solange der Kundenstamm aus dem Altsystem kommt, ersetzt der nächste Import alle Änderungen;
jede Seite sagt das, und der Prüfbericht des Imports warnt. Jede Änderung steht im
Änderungsprotokoll, der Haushalt merkt sich, wann und von wem er geändert wurde.
"""

from django.contrib import messages
from django.db import transaction
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.adressen.forms import AdressKategorieForm
from apps.adressen.models import AdressKategorie
from apps.ausgabe import konto
from apps.ausgabe.forms import BeitragsfreiForm
from apps.ausgabe.models import BeitragsfreierZeitraum, Teilnahme
from apps.core import privatdateien
from apps.core.models import TafelEinstellungen
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden import ausweis, historie, zugang
from apps.kunden.forms_bearbeiten import (
    AbholerForm,
    AnmerkungForm,
    AusgabestelleForm,
    AusnahmeForm,
    AusweisVorlageForm,
    DokumentartForm,
    EinkommensartForm,
    HaushaltForm,
    KundengruppeForm,
    NotizVorlageForm,
    PersonForm,
    SperreForm,
)
from apps.kunden.forms_neu import AngehoerigeFormset, HauptpersonForm, HaushaltNeuForm
from apps.kunden.models import (
    Abholer,
    Abholung,
    Ausgabestelle,
    Ausnahme,
    AusweisVorlage,
    Bemerkung,
    Dokumentart,
    Einkommensart,
    Haushalt,
    HaushaltDokument,
    HaushaltEreignis,
    Kundengruppe,
    Notiz,
    NotizVorlage,
    Person,
    Sperre,
)

# Art in der Adresse: Modell, Formular, Bezeichnung, braucht „angemeldet“
TEILE = {
    "person": (Person, PersonForm, "Person", False),
    "abholer": (Abholer, AbholerForm, "Abholberechtigte Person", False),
    "sperre": (Sperre, SperreForm, "Sperre", True),
    "anmerkung": (Bemerkung, AnmerkungForm, "Anmerkung", True),
    "ausnahme": (Ausnahme, AusnahmeForm, "Ausnahme", True),
}


def geaendert(h: Haushalt, request) -> None:
    Haushalt.objects.filter(pk=h.pk).update(
        geaendert_am=timezone.now(), geaendert_von=request.user.get_username()
    )


def _festhalten(h: Haushalt, vorher, request, zusatz: str = "") -> None:
    historie.festhalten(
        h.kundennummer, vorher, historie.schnappschuss(h),
        quelle=HaushaltEreignis.Quelle.BEARBEITUNG, von=request.user.get_username(),
        zusatz=zusatz,
    )  # fmt: skip


def _bearbeiten_url(h) -> str:
    return reverse("kunden:bearbeiten", args=[h.kundennummer])


@rollen.recht_erforderlich("kunden.bearbeiten")
def haushalt_bearbeiten(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    form = HaushaltForm(request.POST or None, instance=h)
    if not rollen.hat_recht(request.user, "kunden.nummer_aendern"):
        del form.fields["kundennummer"]
    if request.method == "POST" and form.is_valid():
        vorher = historie.schnappschuss(h)
        with transaction.atomic():
            h = form.save()
            if h.kundennummer != kundennummer:  # Notizen, Dokumente, Historie ziehen mit um
                for modell in (Notiz, HaushaltDokument, HaushaltEreignis, Teilnahme):
                    modell.objects.filter(kundennummer=kundennummer).update(
                        kundennummer=h.kundennummer
                    )
            geaendert(h, request)
            _festhalten(h, vorher, request)
        messages.success(request, "Haushalt gespeichert.")
        return redirect(_bearbeiten_url(h))
    return render(
        request,
        "kunden/bearbeiten.html",
        {
            "h": h,
            "form": form,
            "teile": [
                ("person", "Personen", h.personen.all()),
                ("abholer", "Abholberechtigte", h.abholer.all()),
                ("sperre", "Sperren", h.sperren.all()),
                ("ausnahme", "Ausnahmen", h.ausnahmen.all()),
                ("anmerkung", "Interne Anmerkungen", h.bemerkungen.all()),
            ],
            "abholungen": h.abholungen.select_related("ausgabestelle")[:50],
        },
    )


@rollen.recht_erforderlich("kunden.bearbeiten")
def haushalt_neu(request):
    """Ein Formular in der Reihenfolge des Büros: Hauptperson zuerst, Kundengruppe zuletzt."""
    daten = request.POST or None
    nummer_aendern = rollen.hat_recht(request.user, "kunden.nummer_aendern")
    haushalt = HaushaltNeuForm(daten, instance=Haushalt(), nummer_aendern=nummer_aendern)
    hauptperson = HauptpersonForm(daten, prefix="hp", instance=Person(ist_hauptperson=True))
    angehoerige = AngehoerigeFormset(daten, prefix="a", queryset=Person.objects.none())
    if request.method == "POST" and all(
        [haushalt.is_valid(), hauptperson.is_valid(), angehoerige.is_valid()]
    ):
        with transaction.atomic():
            h = haushalt.save()
            hp = hauptperson.save(commit=False)
            hp.haushalt, hp.ist_hauptperson = h, True
            hp.save()
            for f in angehoerige.forms:
                if f.cleaned_data.get("vorname"):
                    p = f.save(commit=False)
                    p.haushalt, p.ist_hauptperson = h, False
                    p.nachname = p.nachname or hp.nachname
                    p.save()
            geaendert(h, request)
            _festhalten(h, None, request, zusatz="Angelegt")
        messages.success(request, f"Haushalt {h.kundennummer} angelegt.")
        return redirect("kunden:haushalt", kundennummer=h.kundennummer)
    return render(request, "kunden/haushalt_neu.html", {
        "haushalt": haushalt, "hauptperson": hauptperson, "angehoerige": angehoerige,
        "hp_felder": [hauptperson[n] for n in hauptperson.fields if not n.startswith("zusatz_")],
        "anschrift": [haushalt[n] for n in ("strasse", "plz", "ort", "telefon", "email")
                      if n in haushalt.fields],
        "zusatz": [haushalt[n] for n in haushalt.fields if n.startswith("zusatz_")],
        "hp_zusatz": [hauptperson[n] for n in hauptperson.fields if n.startswith("zusatz_")],
    })  # fmt: skip


@rollen.recht_erforderlich("kunden.loeschen")
def haushalt_loeschen(request, kundennummer):
    """Erst eine Seite, die aufzählt, was gelöscht wird; gelöscht wird nur nach Bestätigung."""
    h = zugang.haushalt(request.user, kundennummer)
    if request.method != "POST":
        hp = h.hauptperson
        umfang = [
            ("Personen", h.personen.count()),
            ("Abholberechtigte", h.abholer.count()),
            ("Sperren", h.sperren.count()),
            ("Ausnahmen", h.ausnahmen.count()),
            ("Abholungen", h.abholungen.count()),
            ("Interne Anmerkungen", h.bemerkungen.count()),
            ("Notizen", Notiz.objects.filter(kundennummer=kundennummer).count()),
            (
                "Teilnahmen an Sonderaktionen",
                Teilnahme.objects.filter(kundennummer=kundennummer).count(),
            ),
            ("Dokumente", HaushaltDokument.objects.filter(kundennummer=kundennummer).count()),
            (
                "Einträge der Historie",
                HaushaltEreignis.objects.filter(kundennummer=kundennummer).count(),
            ),
        ]
        return render(
            request,
            "kunden/haushalt_loeschen.html",
            {"h": h, "name": f"{hp.vorname} {hp.nachname}" if hp else "", "umfang": umfang,
             "buchungen": h.buchungen.count()},
        )  # fmt: skip
    with transaction.atomic():
        h.delete()  # Buchungen bleiben ohne Haushalt, aber mit Kundennummer (Kasse)
        Notiz.objects.filter(kundennummer=kundennummer).delete()
        HaushaltEreignis.objects.filter(kundennummer=kundennummer).delete()
        Teilnahme.objects.filter(kundennummer=kundennummer).delete()
        dokumente = HaushaltDokument.objects.filter(kundennummer=kundennummer)
        dateien = list(dokumente.values_list("datei", flat=True))
        dokumente.delete()
        transaction.on_commit(
            lambda: [privatdateien.loeschen(HaushaltDokument.ORDNER, d) for d in dateien]
        )
    messages.success(
        request,
        f"Haushalt {kundennummer} gelöscht. Kontobuchungen bleiben ohne Haushalt für die Kasse "
        "erhalten.",
    )
    return redirect("kunden:uebersicht")


def _teil(art):
    if art not in TEILE:
        raise Http404
    return TEILE[art]


@rollen.recht_erforderlich("kunden.bearbeiten")
def teil_bearbeiten(request, kundennummer, art, pk=None):
    h = zugang.haushalt(request.user, kundennummer)
    modell, form_klasse, bezeichnung, mit_angemeldet = _teil(art)
    instanz = get_object_or_404(modell, pk=pk, haushalt=h) if pk else modell(haushalt=h)
    extra = {"angemeldet": request.user} if mit_angemeldet else {}
    form = form_klasse(request.POST or None, instance=instanz, **extra)
    if request.method == "POST" and form.is_valid():
        vorher = historie.schnappschuss(h)
        with transaction.atomic():
            eintrag = form.save(commit=False)
            eintrag.haushalt = h
            if art == "ausnahme" and not eintrag.erfasst_am:
                eintrag.erfasst_am = timezone.now()
            if art == "person" and eintrag.ist_hauptperson:  # nur eine Hauptperson je Haushalt
                h.personen.exclude(pk=eintrag.pk).update(ist_hauptperson=False)
            eintrag.save()
            geaendert(h, request)
            _festhalten(h, vorher, request)
        messages.success(request, f"{bezeichnung} gespeichert.")
        return redirect(_bearbeiten_url(h))
    return render(
        request,
        "kunden/eintrag.html",
        {
            "form": form,
            "h": h,
            "titel": f"{bezeichnung} {'bearbeiten' if pk else 'hinzufügen'}",
            "loeschen": reverse("kunden:teil_loeschen", args=[h.kundennummer, art, pk])
            if pk
            else None,
            "loeschen_frage": f"{bezeichnung} „{instanz}“ aus Haushalt {h.kundennummer} "
            "endgültig löschen?"
            if pk
            else "",
        },
    )


@require_POST
@rollen.recht_erforderlich("kunden.bearbeiten")
def teil_loeschen(request, kundennummer, art, pk):
    h = zugang.haushalt(request.user, kundennummer)
    modell, _, bezeichnung, _ = _teil(art)
    vorher = historie.schnappschuss(h)
    get_object_or_404(modell, pk=pk, haushalt=h).delete()
    geaendert(h, request)
    _festhalten(h, vorher, request)
    messages.success(request, f"{bezeichnung} gelöscht.")
    return redirect(_bearbeiten_url(h))


@require_POST
@rollen.recht_erforderlich("kunden.bearbeiten")
def abholung_loeschen(request, kundennummer, pk):
    """Löscht eine Abholung; eine zugehörige Buchung wird zurückgenommen (Kontostand)."""
    h = zugang.haushalt(request.user, kundennummer)
    abholung = get_object_or_404(Abholung, pk=pk, haushalt=h)
    with transaction.atomic():
        konto.abholung_zuruecknehmen(abholung)
        letzte = h.abholungen.order_by("-datum").first()
        Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=letzte.datum if letzte else None)
        geaendert(h, request)
    messages.success(request, "Abholung gelöscht.")
    return redirect(_bearbeiten_url(h))


# --- Listen ---------------------------------------------------------------------------------

LISTEN = {
    "kundengruppen": (Kundengruppe, KundengruppeForm, "Kundengruppen", "Kundengruppe"),
    "ausgabestellen": (Ausgabestelle, AusgabestelleForm, "Ausgabestellen", "Ausgabestelle"),
    "einkommensarten": (Einkommensart, EinkommensartForm, "Einkommensarten", "Einkommensart"),
    "notizvorlagen": (NotizVorlage, NotizVorlageForm, "Notiz-Vorlagen", "Notiz-Vorlage"),
    "dokumentarten": (Dokumentart, DokumentartForm, "Dokumentarten", "Dokumentart"),
    "adresskategorien": (
        AdressKategorie,
        AdressKategorieForm,
        "Adresskategorien",
        "Adresskategorie",
    ),
    "beitragsfrei": (
        BeitragsfreierZeitraum,
        BeitragsfreiForm,
        "Beitragsfreie Zeiträume",
        "Beitragsfreier Zeitraum",
    ),
}


def _liste(art):
    if art not in LISTEN:
        raise Http404
    return LISTEN[art]


@rollen.recht_erforderlich("einstellungen.listen")
def liste(request, art):
    if art == "ausgabestellen":
        return redirect("kunden:ausgabestellen")
    modell, _, titel, _ = _liste(art)
    return render(
        request,
        "kunden/liste_pflegen.html",
        {"art": art, "titel": titel, "eintraege": modell.objects.all(), "listen": LISTEN},
    )


@rollen.recht_erforderlich("einstellungen.listen")
def listeneintrag(request, art, pk=None):
    if art == "ausgabestellen":  # eigene Seiten mit Zeiten und Ansprechpartnern (ADR 0048)
        if pk:
            return redirect("kunden:ausgabestelle_bearbeiten", pk=pk)
        return redirect("kunden:ausgabestelle_neu")
    modell, form_klasse, titel, einzeln = _liste(art)
    instanz = get_object_or_404(modell, pk=pk) if pk else modell()
    form = form_klasse(request.POST or None, instance=instanz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{einzeln} gespeichert.")
        return redirect("kunden:liste", art=art)
    return render(
        request,
        "kunden/eintrag.html",
        {
            "form": form,
            "titel": f"{einzeln} {'bearbeiten' if pk else 'hinzufügen'}",
            "zurueck": reverse("kunden:liste", args=[art]),
            "loeschen": reverse("kunden:listeneintrag_loeschen", args=[art, pk]) if pk else None,
            "loeschen_frage": f"{einzeln} „{instanz}“ endgültig löschen?" if pk else "",
        },
    )


@require_POST
@rollen.recht_erforderlich("einstellungen.listen")
def listeneintrag_loeschen(request, art, pk):
    modell, _, _, einzeln = _liste(art)
    eintrag = get_object_or_404(modell, pk=pk)
    try:
        eintrag.delete()
    except ProtectedError:
        messages.error(
            request,
            f"{einzeln} wird noch verwendet und kann nicht gelöscht werden. "
            "Stattdessen „Aktiv“ ausschalten.",
        )
    else:
        messages.success(request, f"{einzeln} gelöscht.")
    return redirect("kunden:liste", art=art)


# --- Ausweis gestalten (ADR 0027) -------------------------------------------------------------


@rollen.recht_erforderlich("einstellungen.ausweis")
def ausweis_gestalten(request):
    vorlage = AusweisVorlage.laden()
    form = AusweisVorlageForm(request.POST or None, request.FILES or None, instance=vorlage)
    if request.method == "POST" and form.is_valid():
        if "vorschau" in request.POST:
            return pdf_antwort(
                ausweis.beispiel_pdf(form.instance, form.cleaned_data["vorne"],
                                     form.cleaned_data["hinten"]),
                "ausweis-vorschau.pdf",
            )  # fmt: skip
        if "standard" in request.POST:
            form.instance.vorderseite = []
            form.instance.rueckseite = []
            AusweisVorlage.save(form.instance)
            messages.success(request, "Ausweis auf die Standard-Gestaltung zurückgesetzt.")
            return redirect("kunden:ausweis_gestalten")
        form.save()
        messages.success(request, "Ausweis gespeichert.")
        return redirect("kunden:ausweis_gestalten")
    vorlage = AusweisVorlage.laden()  # Bilder wie gespeichert, auch nach einem Fehler
    tafel = TafelEinstellungen.laden()
    daten = {
        "typen": {t: {"name": n, "pflicht": p, "art": a} for t, (n, p, a) in ausweis.TYPEN.items()},
        "beispiel": {**ausweis.BEISPIEL, "ausweisname": vorlage.name},
        "platzhalter": ausweis.PLATZHALTER,
        "masse": {"b": ausweis.BREITE_MM, "h": ausweis.HOEHE_MM,
                  "barcode_b": ausweis.BARCODE_MIN_B, "barcode_h": ausweis.BARCODE_MIN_H},
        "logo": tafel.logo.url if tafel.logo else "",
        "hintergrund": vorlage.hintergrund.url if vorlage.hintergrund else "",
        "hintergrund_hinten": vorlage.hintergrund_rueckseite.url
        if vorlage.hintergrund_rueckseite
        else "",
    }  # fmt: skip
    return render(request, "kunden/ausweis_gestalten.html", {"form": form, "daten": daten})
