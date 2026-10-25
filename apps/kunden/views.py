import datetime as dt
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.db.models.functions import Length
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.ausgabe.ampel import WOCHENTAGE
from apps.ausgabe.models import AusgabeEinstellungen
from apps.core import sicherung
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden import auskunft as kunden_auskunft
from apps.kunden import export, gruppen, importieren, views_dokumente, zugang
from apps.kunden.ausweis import MAX_SAMMELDRUCK, ausweis_pdf, ausweise_pdf
from apps.kunden.forms import KundenEinstellungenForm, ZusatzfeldForm
from apps.kunden.models import (
    Abholer,
    Abholung,
    Ausnahme,
    Bemerkung,
    Haushalt,
    HaushaltEreignis,
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


@rollen.recht_erforderlich("einstellungen.kundenstamm")
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


@rollen.recht_erforderlich("einstellungen.kundenstamm")
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
    haushalte = (
        zugang.filtern(Haushalt.objects, request.user)
        .select_related("kundengruppe")
        .annotate(
            hp_vorname=Subquery(hauptperson.values("vorname")[:1]),
            hp_nachname=Subquery(hauptperson.values("nachname")[:1]),
            besuch_zeit=Subquery(
                Abholung.objects.filter(haushalt=OuterRef("pk"), datum=OuterRef("letzter_besuch"),
                                        uhrzeit__isnull=False)
                .order_by("-uhrzeit").values("uhrzeit")[:1]
            ),
        )
    )  # fmt: skip
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
    tag = _tag(request)
    haushalte = export.nach_tag(haushalte, tag)
    sortierung = request.GET.get("sort", "")
    if not _sortierbar(sortierung.lstrip("-"), rollen.rechte_von(request.user)):
        sortierung = ""
    if sortierung.lstrip("-") == "personen":
        haushalte = haushalte.annotate(anzahl_personen=Count("personen"))
    haushalte = haushalte.order_by(*_reihenfolge(sortierung or "kundennummer"))
    return haushalte, {"q": suche, "status": status, "gruppe": gruppe, "tag": tag,
                       "sort": sortierung}  # fmt: skip


# Sortierbare Spalten der Kundenliste (Schlüssel wie im Export, ?sort=…, mit „-“ absteigend):
# Felder für order_by; Spalten mit Recht nur sortierbar, wenn das Konto das Recht hat.
SORTIERUNG = {
    "kundennummer": (Length("kundennummer"), "kundennummer"),
    "vorname": ("hp_vorname", "hp_nachname"),
    "nachname": ("hp_nachname", "hp_vorname"),
    "kundengruppe": ("kundengruppe__name",),
    "ausgabestelle": ("kundengruppe__ausgabestelle__name",),
    "wochentage": ("kundengruppe__wochentage",),
    "uhrzeit": ("kundengruppe__uhrzeit",),
    "status": ("status",),
    "personen": ("anzahl_personen",),
    "ausweis": ("ausweis_gueltig_bis",),
    "letzter_besuch": ("letzter_besuch", "besuch_zeit"),
    "kontostand": ("kontostand",),
    "strasse": ("strasse",),
    "plz": ("plz",),
    "ort": ("ort",),
    "telefon": ("telefon",),
    "email": ("email",),
}
_RECHT = {k: r for k, _, r in export.FELDER}


def _sortierbar(schluessel: str, darf) -> bool:
    return schluessel in SORTIERUNG and (not _RECHT.get(schluessel) or _RECHT[schluessel] in darf)


def _reihenfolge(sortierung: str) -> list:
    """Felder für order_by, danach die Kundennummer; leere Werte stehen immer am Ende."""
    ab = sortierung.startswith("-")
    felder = []
    for f in (*SORTIERUNG[sortierung.lstrip("-")], *SORTIERUNG["kundennummer"]):
        ausdruck = F(f) if isinstance(f, str) else f
        felder.append(ausdruck.desc(nulls_last=True) if ab else ausdruck.asc(nulls_last=True))
    return felder


def listen_spalten(benutzer) -> list[str]:
    """Spalten der Kundenliste: wie in den Einstellungen gewählt, ohne die selbst ausgeblendeten;
    die Kundennummer steht immer vorn (sie öffnet den Haushalt)."""
    aus = set(getattr(benutzer, "kundenliste_aus", None) or [])
    keys = [k for k in export.spalten() if k not in aus and k != "kundennummer"]
    return ["kundennummer", *keys]


def _spalten(filter_, keys, darf) -> list[dict]:
    """Spaltenköpfe mit Link: erster Klick aufsteigend, zweiter absteigend."""
    aktuell = filter_["sort"] or "kundennummer"
    grund = {k: v for k, v in filter_.items() if v and k != "sort"} | {"tag": filter_["tag"]}
    namen = dict(export.auswahl())
    spalten = []
    for k in keys:
        titel = "Nr." if k == "kundennummer" else namen[k].removeprefix("Zusatzfeld: ")
        if not _sortierbar(k, darf):
            spalten.append({"titel": titel, "abfrage": "", "richtung": ""})
            continue
        neu = f"-{k}" if aktuell == k else k
        richtung = "auf" if aktuell == k else "ab" if aktuell == f"-{k}" else ""
        spalten.append({"titel": titel, "abfrage": urlencode(grund | {"sort": neu}),
                        "richtung": richtung})  # fmt: skip
    return spalten


def _zeilen(seite, keys, spalten, darf) -> list[dict]:
    """Je Haushalt die Zellen (Text wie im Export, nur mit Rechten), mit Warnfarbe."""
    heute = timezone.localdate()
    zusatzfelder = {z.schluessel: z for z in Zusatzfeld.objects.all()}
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    zeilen = []
    for h in seite:
        werte = export.zeile(h, keys, darf, zusatzfelder, kind_bis, heute)
        warnung = {
            "status": h.status != Haushalt.Status.AKTIV,
            "ausweis": bool(h.ausweis_gueltig_bis and h.ausweis_gueltig_bis < heute),
        }
        zeilen.append({"h": h, "zellen": [
            {"titel": s["titel"], "text": w, "warnung": warnung.get(k, False),
             "link": k in ("kundennummer", "vorname", "nachname")}
            for k, w, s in zip(keys, werte, spalten, strict=True)]})  # fmt: skip
    return zeilen


def _eigene_gruppen(benutzer):
    stellen = zugang.stellen(benutzer)
    gruppen = Kundengruppe.objects.filter(aktiv=True)
    return gruppen if stellen is None else gruppen.filter(ausgabestelle__in=stellen)


def _tag(request) -> str:
    """Gewählter Ausgabetag; ohne Angabe (und ohne Suchtext) der eigene Ausgabetag."""
    if "tag" in request.GET:
        return request.GET["tag"] if request.GET["tag"] in WOCHENTAGE else ""
    if request.GET.get("q", "").strip():
        return ""
    verfuegbar = export.verfuegbare_tage(_eigene_gruppen(request.user))
    return export.standard_tag(request.user, timezone.localdate(), verfuegbar)


@require_POST
@rollen.recht_erforderlich("kunden.liste")
def spalten_waehlen(request):
    """Eigene Auswahl der Spalten in der Kundenliste (am Konto gespeichert)."""
    gewaehlt = set(request.POST.getlist("spalte"))
    request.user.kundenliste_aus = [k for k in export.spalten()
                                    if k != "kundennummer" and k not in gewaehlt]  # fmt: skip
    request.user.save(update_fields=["kundenliste_aus"])
    zurueck = QueryDict(request.POST.get("zurueck", "")).urlencode()  # nur Filterwerte
    return redirect(f"{reverse('kunden:uebersicht')}?{zurueck}")


@rollen.recht_erforderlich("kunden.liste")
def uebersicht(request):
    """Kundenliste mit Suche. Eine exakt passende Kundennummer (Scanner) öffnet den Haushalt."""
    ImportVorbereitung.abgelaufene_loeschen()
    fristen_anwenden()
    suche = request.GET.get("q", "").strip()
    if suche and not request.headers.get("HX-Request"):
        treffer = (
            Haushalt.objects.select_related("kundengruppe__ausgabestelle")
            .filter(kundennummer__iexact=suche)
            .first()
        )
        grund = zugang.sperrgrund(request.user, treffer) if treffer else ""
        if treffer and not grund:
            return redirect("kunden:haushalt", kundennummer=treffer.kundennummer)
        if grund:
            messages.error(request, grund)
    haushalte, filter_ = _haushalte_suchen(request)
    seite = Paginator(haushalte.select_related("kundengruppe__ausgabestelle")
                      .prefetch_related("personen"), LISTE_JE_SEITE).get_page(
        request.GET.get("seite"))  # fmt: skip
    darf = rollen.rechte_von(request.user)
    keys = listen_spalten(request.user)
    aus = set(request.user.kundenliste_aus or [])
    spalten = _spalten(filter_, keys, darf)
    kontext = {
        "seite": seite,
        "filter": filter_,
        "status_auswahl": Haushalt.Status.choices,
        "gruppen": Kundengruppe.objects.order_by("name")
        if zugang.stellen(request.user) is None
        else Kundengruppe.objects.filter(ausgabestelle__in=zugang.stellen(request.user)),
        "eigene_stellen": zugang.stellen(request.user),
        "tage": export.verfuegbare_tage(_eigene_gruppen(request.user)),
        "abfrage": urlencode({k: v for k, v in filter_.items() if v} | {"tag": filter_["tag"]}),
        "spalten": spalten,
        "zeilen": _zeilen(seite, keys, spalten, darf),
        "spalten_wahl": [
            (k, n, k not in aus)
            for k, n in export.auswahl()
            if k in export.spalten() and k != "kundennummer"
        ],
        "heute": timezone.localdate(),
        "darf_importieren": rollen.hat_recht(request.user, "kunden.importieren"),
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


@rollen.recht_erforderlich("kunden.ansehen")
def haushalt(request, kundennummer):
    """Detailansicht eines Haushalts. Jeder Aufruf steht im Zugriffsprotokoll."""
    h = zugang.haushalt(
        request.user,
        kundennummer,
        Haushalt.objects.select_related("einkommensart").prefetch_related(
            "personen", "abholer", "sperren", "ausnahmen"
        ),
    )
    einstellungen = KundenEinstellungen.laden()
    darf = rollen.rechte_von(request.user)
    art9 = "kunden.besondere_kategorie" in darf

    felder = Zusatzfeld.objects.filter(aktiv=True)
    if not art9:
        felder = felder.exclude(besondere_kategorie=True)
    haushalt_felder = [f for f in felder if f.gilt_fuer == Zusatzfeld.GiltFuer.HAUSHALT]
    person_felder = [f for f in felder if f.gilt_fuer == Zusatzfeld.GiltFuer.PERSON]

    personen = [(p, _zusatz_anzeigen(person_felder, p.zusatz)) for p in h.personen.all()]
    haushalt_zusatz = _zusatz_anzeigen(haushalt_felder, h.zusatz)
    heute = timezone.localdate()
    sperren = [(s, s.ist_aktiv(heute)) for s in h.sperren.all()]
    if "kunden.sperren_alle" not in darf:
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
            "einstellungen": einstellungen,
            "hauptperson": next((p for p in personen if p[0].ist_hauptperson), None),
            "angehoerige": [p for p in personen if not p[0].ist_hauptperson],
            "haushalt_zusatz": haushalt_zusatz,
            "erwachsene": erwachsene,
            "kinder": kinder,
            "sperren": sperren,
            "ausnahmen": h.ausnahmen.all()[
                : None if "kunden.sperren_alle" in darf else ABHOLUNGEN_AUSGABE
            ],
            "abholungen": abholungen[
                : ABHOLUNGEN_BUERO if "kunden.abholungen_alle" in darf else ABHOLUNGEN_AUSGABE
            ],
            "abholungen_gesamt": abholungen.count(),
            "bemerkungen": h.bemerkungen.all() if "kunden.anmerkungen" in darf else [],
            **notizen_kontext(h.kundennummer, request.user),
            **(views_dokumente.kontext(h.kundennummer) if "kunden.dokumente" in darf else {}),
            "gruppenzeiten": gruppen.zeiten(h.kundennummer) if "kunden.historie" in darf else [],
            "historie": HaushaltEreignis.objects.filter(kundennummer=h.kundennummer)
            if "kunden.historie" in darf
            else [],
            "kontostand_zeigen": "kunden.konto" in darf
            or AusgabeEinstellungen.laden().kontostand_anzeigen,
            "buchungen": h.buchungen.all() if "kunden.konto" in darf else [],
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
@rollen.recht_erforderlich("kunden.notizen")
def notiz_neu(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    if notiz_schreiben(h, request.POST.get("text", ""), request.user):
        messages.success(request, "Notiz gespeichert.")
    else:
        messages.error(request, "Bitte einen Text eingeben.")
    return redirect("kunden:haushalt", kundennummer=h.kundennummer)


@require_POST
@rollen.recht_erforderlich("kunden.notizen")
def notiz_loeschen(request, pk):
    notiz = get_object_or_404(Notiz, pk=pk)
    zugang.pruefen_nummer(request.user, notiz.kundennummer)
    if not notiz.darf_loeschen(request.user):
        raise PermissionDenied
    notiz.delete()
    messages.success(request, "Notiz gelöscht.")
    return redirect("kunden:haushalt", kundennummer=notiz.kundennummer)


@never_cache
@rollen.recht_erforderlich("kunden.auskunft")
def auskunft(request, kundennummer):
    """Auskunft nach Art. 15 DSGVO als PDF; steht wie jeder Aufruf im Zugriffsprotokoll."""
    h = zugang.haushalt(request.user, kundennummer)
    Zugriff.objects.create(
        benutzer=request.user,
        benutzername=request.user.get_username(),
        kundennummer=h.kundennummer,
        besondere_kategorie=kunden_auskunft.hat_besondere_kategorie(h),
    )
    return pdf_antwort(kunden_auskunft.kunde_pdf(h), f"auskunft-{_dateiname(h)}.pdf")


@never_cache
@rollen.recht_erforderlich("kunden.ausweis")
def ausweis(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    return pdf_antwort(ausweis_pdf(h), f"kundenausweis-{_dateiname(h)}.pdf")


@never_cache
@rollen.recht_erforderlich("kunden.exportieren")
def exportieren(request):
    """Gefilterte Kundenliste der eigenen Ausgabestellen als CSV; jeder Haushalt ins Protokoll."""
    haushalte, filter_ = _haushalte_suchen(request)
    haushalte = list(haushalte.select_related("kundengruppe__ausgabestelle")
                     .prefetch_related("personen"))  # fmt: skip
    heute = timezone.localdate()
    inhalt = export.csv_text(haushalte, rollen.rechte_von(request.user), heute)
    jetzt = timezone.now()
    Zugriff.objects.bulk_create([
        Zugriff(zeitpunkt=jetzt, benutzer=request.user, benutzername=request.user.get_username(),
                kundennummer=h.kundennummer, export=True)
        for h in haushalte
    ])  # fmt: skip
    teil = f"-{filter_['tag'].lower()}" if filter_["tag"] else ""
    antwort = HttpResponse(inhalt, content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = f'attachment; filename="kunden{teil}-{heute:%Y-%m-%d}.csv"'
    return antwort


@never_cache
@rollen.recht_erforderlich("kunden.ausweis")
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


@rollen.recht_erforderlich("kunden.zugriffsprotokoll")
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


@rollen.recht_erforderlich("kunden.importieren")
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


@rollen.recht_erforderlich("kunden.importieren")
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
            "abgleich": importieren.abgleich(daten),
            "max_abgleich": importieren.MAX_ABGLEICH,
        },
    )


@require_POST
@rollen.recht_erforderlich("kunden.importieren")
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
    # Haushalte, die in bintafeln geändert oder aufgenommen wurden: je Haushalt gewählt
    fragen = {e["kundennummer"] for e in importieren.abgleich(vorbereitung.daten)["fragen"]}
    behalten = {n for n in fragen if request.POST.get(f"wahl_{n}", "behalten") == "behalten"}
    if request.POST.get("alle") == "uebernehmen":
        behalten = set()
    lauf = importieren.uebernehmen(
        vorbereitung.daten,
        benutzer=request.user,
        dateien=vorbereitung.dateien,
        pruefsumme=vorbereitung.pruefsumme,
        anzahl_warnungen=len(vorbereitung.bericht),
        behalten=behalten,
    )
    vorbereitung.delete()
    messages.success(
        request,
        f"Import abgeschlossen: {lauf.anzahl_haushalte} Haushalte, "
        f"{lauf.anzahl_personen} Personen."
        + (f" {len(behalten)} Haushalt(e) mit bintafeln-Stand behalten." if behalten else ""),
    )
    return redirect("kunden:uebersicht")


@require_POST
@rollen.recht_erforderlich("kunden.importieren")
def import_verwerfen(request, pk):
    vorbereitung = _vorbereitung_laden(request, pk)
    if vorbereitung is not None:
        vorbereitung.delete()
    messages.info(request, "Import verworfen. Die geprüften Daten wurden gelöscht.")
    return redirect("kunden:import")
