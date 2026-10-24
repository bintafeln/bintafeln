import datetime as dt

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.ausgabe.models import AusgabeEinstellungen
from apps.core import sicherung
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden import auskunft as kunden_auskunft
from apps.kunden import importieren
from apps.kunden.ausweis import MAX_SAMMELDRUCK, ausweis_pdf, ausweise_pdf
from apps.kunden.forms import KundenEinstellungenForm, ZusatzfeldForm
from apps.kunden.models import (
    Abholer,
    Abholung,
    Ausnahme,
    Bemerkung,
    Haushalt,
    ImportLauf,
    ImportVorbereitung,
    KundenEinstellungen,
    Kundengruppe,
    Notiz,
    NotizVorlage,
    Person,
    Sperre,
    Zugriff,
    Zusatzfeld,
    fristen_anwenden,
)


@rollen.rolle_erforderlich(rollen.ADMIN)
def einstellungen(request):
    form = KundenEinstellungenForm(request.POST or None, instance=KundenEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen des Kundenstamms gespeichert.")
        return redirect("kunden:einstellungen")
    return render(
        request,
        "kunden/einstellungen.html",
        {"form": form, "zusatzfelder": Zusatzfeld.objects.all()},
    )


@rollen.rolle_erforderlich(rollen.ADMIN)
def zusatzfeld_bearbeiten(request, pk=None):
    feld = get_object_or_404(Zusatzfeld, pk=pk) if pk else Zusatzfeld()
    form = ZusatzfeldForm(request.POST or None, instance=feld)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Zusatzfeld „{feld.bezeichnung}“ gespeichert.")
        return redirect("kunden:einstellungen")
    return render(request, "kunden/zusatzfeld.html", {"form": form, "feld": feld})


# --- Übersicht und Import ---------------------------------------------------------------

MAX_DATEIGROESSE = 20 * 1024 * 1024
MAX_SICHERUNGSALTER = dt.timedelta(hours=24)


def _sicherung_frisch() -> bool:
    status = sicherung.lese_status()
    return (
        status.letzte_erfolgreiche is not None
        and timezone.now() - status.letzte_erfolgreiche <= MAX_SICHERUNGSALTER
    )


LISTE_JE_SEITE = 50
ABHOLUNGEN_AUSGABE = 5
ABHOLUNGEN_BUERO = 20


def _haushalte_suchen(request):
    """Haushalte nach Suchtext, Status und Kundengruppe; mit Name der Hauptperson."""
    hauptperson = Person.objects.filter(haushalt=OuterRef("pk"), ist_hauptperson=True)
    haushalte = Haushalt.objects.select_related("kundengruppe").annotate(
        hp_vorname=Subquery(hauptperson.values("vorname")[:1]),
        hp_nachname=Subquery(hauptperson.values("nachname")[:1]),
    )
    suche = request.GET.get("q", "").strip()
    for wort in suche.split():
        personen = Person.objects.filter(
            Q(vorname__icontains=wort) | Q(nachname__icontains=wort)
        ).values("haushalt")
        haushalte = haushalte.filter(Q(kundennummer__icontains=wort) | Q(pk__in=personen))
    status = request.GET.get("status", "")
    if status in Haushalt.Status.values:
        haushalte = haushalte.filter(status=status)
    gruppe = request.GET.get("gruppe", "")
    if gruppe.isdigit():
        haushalte = haushalte.filter(kundengruppe_id=int(gruppe))
    return haushalte, {"q": suche, "status": status, "gruppe": gruppe}


@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO, rollen.AUSGABE)
def uebersicht(request):
    """Kundenliste mit Suche. Eine exakt passende Kundennummer (Scanner) öffnet den Haushalt."""
    ImportVorbereitung.abgelaufene_loeschen()
    fristen_anwenden()
    suche = request.GET.get("q", "").strip()
    if suche and not request.headers.get("HX-Request"):
        treffer = Haushalt.objects.filter(kundennummer__iexact=suche).first()
        if treffer:
            return redirect("kunden:haushalt", kundennummer=treffer.kundennummer)
    haushalte, filter_ = _haushalte_suchen(request)
    kontext = {
        "seite": Paginator(haushalte, LISTE_JE_SEITE).get_page(request.GET.get("seite")),
        "filter": filter_,
        "status_auswahl": Haushalt.Status.choices,
        "gruppen": Kundengruppe.objects.order_by("name"),
        "heute": timezone.localdate(),
        "darf_importieren": rollen.hat_rolle(request.user, rollen.ADMIN, rollen.BUERO),
        "anzahl": {
            "haushalte": Haushalt.objects.count(),
            "personen": Person.objects.count(),
            "kundengruppen": Kundengruppe.objects.count(),
            "abholungen": Abholung.objects.count(),
        },
    }
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "kunden-liste":
        return render(request, "kunden/_liste.html", kontext)
    return render(request, "kunden/uebersicht.html", kontext)


def _zusatz_anzeigen(felder, werte_) -> list[tuple[str, str, bool]]:
    """(Bezeichnung, Wert, besondere Kategorie) für alle Felder mit Wert."""
    ergebnis = []
    for feld in felder:
        anzeige = feld.wert_anzeigen(werte_.get(feld.schluessel))
        if anzeige:
            ergebnis.append((feld.bezeichnung, anzeige, feld.besondere_kategorie))
    return ergebnis


@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO, rollen.AUSGABE)
def haushalt(request, kundennummer):
    """Detailansicht eines Haushalts. Jeder Aufruf steht im Zugriffsprotokoll."""
    h = get_object_or_404(
        Haushalt.objects.select_related(
            "kundengruppe__ausgabestelle", "einkommensart"
        ).prefetch_related("personen", "abholer", "sperren", "ausnahmen"),
        kundennummer=kundennummer,
    )
    einstellungen = KundenEinstellungen.laden()
    buero = rollen.hat_rolle(request.user, rollen.ADMIN, rollen.BUERO)
    art9 = buero or einstellungen.besondere_kategorie_fuer_ausgabe

    felder = Zusatzfeld.objects.filter(aktiv=True)
    if not art9:
        felder = felder.exclude(besondere_kategorie=True)
    haushalt_felder = [f for f in felder if f.gilt_fuer == Zusatzfeld.GiltFuer.HAUSHALT]
    person_felder = [f for f in felder if f.gilt_fuer == Zusatzfeld.GiltFuer.PERSON]

    personen = [(p, _zusatz_anzeigen(person_felder, p.zusatz)) for p in h.personen.all()]
    haushalt_zusatz = _zusatz_anzeigen(haushalt_felder, h.zusatz)
    heute = timezone.localdate()
    sperren = [(s, s.ist_aktiv(heute)) for s in h.sperren.all()]
    if not buero:
        sperren = [(s, aktiv) for s, aktiv in sperren if aktiv]
    abholungen = h.abholungen.select_related("ausgabestelle")
    zeigt_art9 = any(b for _, _, b in haushalt_zusatz) or any(
        b for _, zusatz in personen for _, _, b in zusatz
    )

    Zugriff.objects.create(
        benutzer=request.user,
        benutzername=request.user.get_username(),
        kundennummer=h.kundennummer,
        besondere_kategorie=zeigt_art9,
    )
    erwachsene, kinder = h.groesse(einstellungen.kind_bis_alter, heute)
    return render(
        request,
        "kunden/haushalt.html",
        {
            "h": h,
            "buero": buero,
            "einstellungen": einstellungen,
            "hauptperson": next((p for p in personen if p[0].ist_hauptperson), None),
            "angehoerige": [p for p in personen if not p[0].ist_hauptperson],
            "haushalt_zusatz": haushalt_zusatz,
            "erwachsene": erwachsene,
            "kinder": kinder,
            "sperren": sperren,
            "ausnahmen": h.ausnahmen.all()[: None if buero else ABHOLUNGEN_AUSGABE],
            "abholungen": abholungen[: ABHOLUNGEN_BUERO if buero else ABHOLUNGEN_AUSGABE],
            "abholungen_gesamt": abholungen.count(),
            "bemerkungen": h.bemerkungen.all() if buero else [],
            **notizen_kontext(h.kundennummer, request.user),
            "kontostand_zeigen": buero or AusgabeEinstellungen.laden().kontostand_anzeigen,
            "buchungen": h.buchungen.all() if buero else [],
            "ausweis_abgelaufen": h.ausweis_gueltig_bis is not None
            and h.ausweis_gueltig_bis < heute,
            "heute": heute,
        },
    )


def notiz_schreiben(h: Haushalt, text: str, benutzer) -> Notiz | None:
    """Legt eine Notiz an; leerer Text legt nichts an."""
    text = text.strip()[:1000]
    if not text:
        return None
    von = (benutzer.get_full_name() or benutzer.get_username())[:100]
    return Notiz.objects.create(
        kundennummer=h.kundennummer, text=text, verfasst_von=von, benutzer=benutzer
    )


def notizen_kontext(kundennummer: str, benutzer) -> dict:
    """Notizen mit der Angabe, ob sie gelöscht werden dürfen, und die aktiven Vorlagen."""
    notizen = list(Notiz.objects.filter(kundennummer=kundennummer))
    for n in notizen:
        n.loeschbar = n.darf_loeschen(benutzer)
    return {"notizen": notizen, "notiz_vorlagen": NotizVorlage.objects.filter(aktiv=True)}


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO, rollen.AUSGABE)
def notiz_neu(request, kundennummer):
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    if notiz_schreiben(h, request.POST.get("text", ""), request.user):
        messages.success(request, "Notiz gespeichert.")
    else:
        messages.error(request, "Bitte einen Text eingeben.")
    return redirect("kunden:haushalt", kundennummer=h.kundennummer)


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO, rollen.AUSGABE)
def notiz_loeschen(request, pk):
    notiz = get_object_or_404(Notiz, pk=pk)
    if not notiz.darf_loeschen(request.user):
        raise PermissionDenied
    notiz.delete()
    messages.success(request, "Notiz gelöscht.")
    return redirect("kunden:haushalt", kundennummer=notiz.kundennummer)


@never_cache
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def auskunft(request, kundennummer):
    """Auskunft nach Art. 15 DSGVO als PDF; steht wie jeder Aufruf im Zugriffsprotokoll."""
    h = get_object_or_404(Haushalt, kundennummer=kundennummer)
    Zugriff.objects.create(
        benutzer=request.user,
        benutzername=request.user.get_username(),
        kundennummer=h.kundennummer,
        besondere_kategorie=kunden_auskunft.hat_besondere_kategorie(h),
    )
    return pdf_antwort(kunden_auskunft.kunde_pdf(h), f"auskunft-{_dateiname(h)}.pdf")


@never_cache
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def ausweis(request, kundennummer):
    h = get_object_or_404(
        Haushalt.objects.select_related("kundengruppe"), kundennummer=kundennummer
    )
    return pdf_antwort(ausweis_pdf(h), f"kundenausweis-{_dateiname(h)}.pdf")


@never_cache
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def ausweise(request):
    """Sammeldruck: Ausweise aller Haushalte der aktuellen Auswahl in der Kundenliste."""
    haushalte, _ = _haushalte_suchen(request)
    haushalte = list(
        haushalte.select_related("kundengruppe__ausgabestelle").order_by("kundennummer")[
            : MAX_SAMMELDRUCK + 1
        ]
    )
    if not haushalte or len(haushalte) > MAX_SAMMELDRUCK:
        messages.error(
            request,
            "Keine Haushalte ausgewählt." if not haushalte else
            f"Mehr als {MAX_SAMMELDRUCK} Haushalte: bitte nach Kundengruppe oder Status filtern.",
        )  # fmt: skip
        return redirect(f"{reverse('kunden:uebersicht')}?{request.GET.urlencode()}")
    return pdf_antwort(ausweise_pdf(haushalte), "kundenausweise.pdf")


def _dateiname(h) -> str:
    return "".join(z if z.isalnum() or z in "-_" else "_" for z in h.kundennummer)


@rollen.rolle_erforderlich(rollen.ADMIN)
def zugriffe(request):
    eintraege = Zugriff.objects.all()
    kundennummer = request.GET.get("kundennummer", "").strip()
    if kundennummer:
        eintraege = eintraege.filter(kundennummer__iexact=kundennummer)
    benutzername = request.GET.get("benutzer", "").strip()
    if benutzername:
        eintraege = eintraege.filter(benutzername__iexact=benutzername)
    return render(
        request,
        "kunden/zugriffe.html",
        {
            "seite": Paginator(eintraege, LISTE_JE_SEITE).get_page(request.GET.get("seite")),
            "kundennummer": kundennummer,
            "benutzer": benutzername,
            "frist": KundenEinstellungen.laden().zugriffe_aufbewahren_tage,
        },
    )


@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_hochladen(request):
    ImportVorbereitung.abgelaufene_loeschen()
    kontext = {
        "sicherung_frisch": _sicherung_frisch(),
        "importe": ImportLauf.objects.select_related("benutzer")[:10],
    }
    if request.method == "POST":
        dateien = request.FILES.getlist("dateien")
        if not dateien:
            messages.error(request, "Bitte mindestens haushalte.csv auswählen.")
            return render(request, "kunden/import.html", kontext)
        zu_gross = [d.name for d in dateien if d.size > MAX_DATEIGROESSE]
        if zu_gross:
            messages.error(request, "Dateien dürfen höchstens 20 MB groß sein.")
            return render(request, "kunden/import.html", kontext)
        ergebnis = importieren.pruefen({d.name: d.read() for d in dateien})
        if ergebnis.daten is None:
            kontext["bericht"] = importieren.bericht_gruppiert(ergebnis.bericht)
            kontext["dateien"] = ergebnis.dateien
            return render(request, "kunden/import.html", kontext)
        vorbereitung = ImportVorbereitung.objects.create(
            erstellt_von=request.user,
            dateien=ergebnis.dateien,
            pruefsumme=ergebnis.pruefsumme,
            daten=ergebnis.daten,
            bericht=ergebnis.bericht,
        )
        return redirect("kunden:import_vorschau", pk=vorbereitung.pk)
    return render(request, "kunden/import.html", kontext)


def _vorbereitung_laden(request, pk):
    ImportVorbereitung.abgelaufene_loeschen()
    return ImportVorbereitung.objects.filter(pk=pk, erstellt_von=request.user).first()


@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_vorschau(request, pk):
    vorbereitung = _vorbereitung_laden(request, pk)
    if vorbereitung is None:
        messages.error(request, "Dieser Import ist abgelaufen oder existiert nicht mehr.")
        return redirect("kunden:import")
    daten = vorbereitung.daten
    return render(
        request,
        "kunden/import_vorschau.html",
        {
            "vorbereitung": vorbereitung,
            "bericht": importieren.bericht_gruppiert(vorbereitung.bericht),
            "anzahl_warnungen": len(vorbereitung.bericht),
            "neu": {
                "haushalte": len(daten["haushalte"]),
                "personen": len(daten["haushalte"]) + len(daten["personen"]),
                "abholer": len(daten["abholer"]),
                "sperren": len(daten["sperren"]),
                "bemerkungen": len(daten["bemerkungen"]),
                "abholungen": len(daten.get("abholungen", [])),
                "ausnahmen": len(daten.get("ausnahmen", [])),
            },
            "bisher": {
                "haushalte": Haushalt.objects.count(),
                "personen": Person.objects.count(),
                "abholer": Abholer.objects.count(),
                "sperren": Sperre.objects.count(),
                "bemerkungen": Bemerkung.objects.count(),
                "abholungen": Abholung.objects.count(),
                "ausnahmen": Ausnahme.objects.count(),
            },
            "gueltig_bis": vorbereitung.erstellt_am + ImportVorbereitung.GUELTIG,
            "sicherung_frisch": _sicherung_frisch(),
        },
    )


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_uebernehmen(request, pk):
    vorbereitung = _vorbereitung_laden(request, pk)
    if vorbereitung is None:
        messages.error(request, "Dieser Import ist abgelaufen oder existiert nicht mehr.")
        return redirect("kunden:import")
    if not _sicherung_frisch():
        messages.error(
            request,
            "Die letzte erfolgreiche Sicherung ist älter als 24 Stunden. Bitte zuerst auf dem "
            "Server „./betrieb sichern“ ausführen.",
        )
        return redirect("kunden:import_vorschau", pk=pk)
    lauf = importieren.uebernehmen(
        vorbereitung.daten,
        benutzer=request.user,
        dateien=vorbereitung.dateien,
        pruefsumme=vorbereitung.pruefsumme,
        anzahl_warnungen=len(vorbereitung.bericht),
    )
    vorbereitung.delete()
    messages.success(
        request,
        f"Import abgeschlossen: {lauf.anzahl_haushalte} Haushalte, "
        f"{lauf.anzahl_personen} Personen.",
    )
    return redirect("kunden:uebersicht")


@require_POST
@rollen.rolle_erforderlich(rollen.ADMIN, rollen.BUERO)
def import_verwerfen(request, pk):
    vorbereitung = _vorbereitung_laden(request, pk)
    if vorbereitung is not None:
        vorbereitung.delete()
    messages.info(request, "Import verworfen. Die geprüften Daten wurden gelöscht.")
    return redirect("kunden:import")
