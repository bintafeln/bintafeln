"""Spenden und Zuwendungsbestätigungen (ADR 0045)."""

import base64
import csv
import io
import re
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.adressen.forms import ImportForm
from apps.adressen.models import Adresse
from apps.core import (
    geheimnis,
    listen,
    listenauswahl,
    listenexport,
    mail,
    papierkorb,
    privatdateien,
)
from apps.core.pdf import im_fenster, pdf_antwort
from apps.konten import rollen
from apps.konten.views import nicht_in_demo
from apps.spenden import bestaetigung as bst
from apps.spenden import dank as danken
from apps.spenden import importieren
from apps.spenden.forms import DankForm, SpendeForm, SpendenEinstellungenForm
from apps.spenden.models import Spende, SpendenBeleg, SpendenEinstellungen, Zuwendungsbestaetigung


def _jahr(request) -> int:
    wert = request.GET.get("jahr", "")
    return int(wert) if wert.isdigit() and 1990 < int(wert) < 2200 else timezone.localdate().year


def _jahre():
    jahre = {d.year for d in Spende.objects.dates("datum", "year")}
    jahre.add(timezone.localdate().year)
    return sorted(jahre, reverse=True)


# Sortierbare Spalten der Spendenliste (Schlüssel wie in ?sort=…, mit „-“ absteigend):
SORTIERUNG = {
    "datum": ("datum", "pk"),
    "spender": ("adresse__organisation", "adresse__nachname", "adresse__vorname"),
    "art": ("art",),
    "betrag": ("betrag",),
}
# Spalten zum Zu-/Abwählen je Person (Datum bleibt immer sichtbar):
SPALTEN = [("datum", "Datum"), ("spender", "Spender"), ("art", "Art"), ("betrag", "Betrag/Wert"),
           ("bezeichnung", "Bezeichnung / Zweck"), ("bestaetigung", "Bestätigung")]  # fmt: skip
SPALTEN_FEST = {"datum"}


@rollen.recht_erforderlich("spenden.sehen")
def liste(request):
    jahr = _jahr(request)
    spenden = Spende.objects.filter(datum__year=jahr).select_related("adresse", "bestaetigung")
    art = request.GET.get("art", "")
    if art in Spende.Art.values:
        spenden = spenden.filter(art=art)
    q = request.GET.get("q", "").strip()
    if q:
        spenden = spenden.filter(
            Q(adresse__organisation__icontains=q) | Q(adresse__nachname__icontains=q)
            | Q(adresse__vorname__icontains=q) | Q(beschreibung__icontains=q)
            | Q(zweck__icontains=q)
        )  # fmt: skip
    spenden, sort = listen.sortieren(spenden, request.GET.get("sort", ""), SORTIERUNG, "-datum")
    if request.GET.get("aktion"):
        return listenexport.ausliefern(request, f"Spenden {jahr}", f"spenden-{jahr}",
                                       _csv_text(listenauswahl.filtern(request, spenden), jahr),
                                       weiter=reverse("spenden:liste"))  # fmt: skip
    summen = spenden.aggregate(
        geld=Sum("betrag", filter=Q(art=Spende.Art.GELD)),
        sach=Sum("betrag", filter=Q(art=Spende.Art.SACH)),
        anzahl=Count("pk"), spender=Count("adresse", distinct=True),
    )  # fmt: skip
    je_monat = (spenden.filter(art=Spende.Art.GELD).values_list("datum__month")
                .annotate(s=Sum("betrag")).order_by("datum__month"))  # fmt: skip
    abfrage = request.GET.copy()
    abfrage.pop("seite", None)
    return render(request, "spenden/liste.html", {
        "seite": Paginator(spenden, 50).get_page(request.GET.get("seite")),
        "jahr": jahr, "jahre": _jahre(), "filter": {"art": art, "q": q}, "summen": summen,
        "je_monat": list(je_monat), "arten": Spende.Art.choices, "sort": sort,
        "sichtbar": listen.sichtbare_spalten(request.user, "spenden",
                                             [k for k, _ in SPALTEN], SPALTEN_FEST),
        "spalten_wahl": listen.spalten_wahl(request.user, "spenden", SPALTEN, SPALTEN_FEST),
        "abfrage": abfrage.urlencode(),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("spenden.sehen")
def spalten(request):
    """Speichert, welche Spalten diese Person in der Spendenliste sieht."""
    listen.spalten_speichern(request.user, "spenden", request.POST.getlist("spalte"),
                             SPALTEN, SPALTEN_FEST)  # fmt: skip
    zurueck = QueryDict(request.POST.get("zurueck", "")).urlencode()
    ziel = reverse("spenden:liste")
    return redirect(f"{ziel}?{zurueck}" if zurueck else ziel)


def _csv_text(spenden, jahr) -> str:
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    w.writerow(
        [
            "Datum",
            "Art",
            "Spender",
            "PLZ",
            "Ort",
            "Betrag/Wert",
            "Mitgliedsbeitrag",
            "Zahlungsweg",
            "Bezeichnung",
            "Menge",
            "Einheit",
            "Zweck",
            "Bestätigung",
        ]
    )
    for s in spenden:
        w.writerow([f"{s.datum:%d.%m.%Y}", s.get_art_display(), s.adresse.name, s.adresse.plz,
                    s.adresse.ort, f"{s.betrag:.2f}".replace(".", ",") if s.betrag else "",
                    "ja" if s.mitgliedsbeitrag else "", s.zahlungsweg, s.beschreibung,
                    s.menge or "", s.einheit, s.zweck,
                    s.bestaetigung.nummer if s.bestaetigt else ""])  # fmt: skip
    return "﻿" + puffer.getvalue()


@never_cache
@rollen.recht_erforderlich("spenden.erfassen")
def bearbeiten(request, pk=None):
    s = get_object_or_404(Spende, pk=pk) if pk else Spende()
    if s.bestaetigt:
        messages.error(request, f"Diese Spende ist mit Zuwendungsbestätigung Nr. "
                                f"{s.bestaetigung.nummer} bestätigt. Zum Ändern die Bestätigung "
                                "zuerst stornieren.")  # fmt: skip
        return redirect("spenden:bestaetigungen")
    initial = {}
    if not pk and request.GET.get("adresse", "").isdigit():
        initial["adresse"] = request.GET["adresse"]
    if not pk and request.GET.get("mitgliedsbeitrag"):  # von der Seite eines Mitglieds
        initial["mitgliedsbeitrag"] = True
        initial["zweck"] = "Mitgliedsbeitrag"
    if not pk and re.fullmatch(r"\d{1,6}(\.\d{1,2})?", request.GET.get("betrag", "")):
        initial["betrag"] = Decimal(request.GET["betrag"])
    form = SpendeForm(request.POST or None, instance=s, initial=initial)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        if not s.eingetragen_von:
            s.eingetragen_von = request.user.get_username()
        s.save()
        messages.success(request, f"{s} von {s.adresse.name} gespeichert.")
        if request.POST.get("weiter"):
            return redirect(reverse("spenden:neu"))
        return redirect("adressen:adresse", pk=s.adresse_id)
    return render(request, "spenden/bearbeiten.html", {"form": form, "s": s})


SITZUNG_IMPORT = "spenden_import"


def _bericht_aus_sitzung(request):
    gespeichert = request.session.get(SITZUNG_IMPORT)
    if not gespeichert:
        return None
    roh = geheimnis.bytes_entschluesseln(base64.b64decode(gespeichert))
    return importieren.pruefen(importieren.text_lesen(roh)) if roh else None


@never_cache
@rollen.recht_erforderlich("spenden.erfassen")
def importieren_ansicht(request):
    """CSV prüfen (Bericht), dann übernehmen; dazwischen verschlüsselt in der Sitzung."""
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
            return redirect("spenden:importieren")
        anzahl = importieren.uebernehmen(bericht, request.user.get_username())
        messages.success(request, f"{anzahl} Spende{'n' if anzahl != 1 else ''} übernommen.")
        return redirect("spenden:liste")
    if request.method == "POST" and form.is_valid():
        roh = form.cleaned_data["datei"].read()
        try:
            bericht = importieren.pruefen(importieren.text_lesen(roh))
        except importieren.ImportFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("spenden:importieren")
        request.session[SITZUNG_IMPORT] = base64.b64encode(
            geheimnis.bytes_verschluesseln(roh)
        ).decode()
    return render(request, "spenden/importieren.html", {
        "form": form, "bericht": bericht, "spalten": importieren.SPALTEN,
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("spenden.erfassen")
def loeschen(request, pk):
    s = get_object_or_404(Spende, pk=pk)
    if s.bestaetigt:
        messages.error(request, "Bestätigte Spenden lassen sich nicht löschen.")
    else:
        papierkorb.loeschen(request.user, "Spende", f"{s} ({s.adresse})", s,
                            recht="spenden.erfassen")  # fmt: skip
        messages.success(request, "Spende in den Papierkorb gelegt.")
    return redirect("adressen:adresse", pk=s.adresse_id)


@never_cache
@rollen.recht_erforderlich("spenden.bestaetigen")
def bestaetigungen(request):
    jahr = _jahr(request)
    e = SpendenEinstellungen.laden()
    ausgestellt = Zuwendungsbestaetigung.objects.filter(
        ausgestellt_am__year=jahr).select_related("adresse")  # fmt: skip
    return render(request, "spenden/bestaetigungen.html", {
        "neu_pdf": request.session.pop("spenden_neu", ""),
        "jahr": jahr, "jahre": _jahre(), "offen": bst.jahresliste(jahr),
        "ausgestellt": ausgestellt, "fehlt": e.fehlende_angaben(),
        "sachspenden": Spende.objects.filter(art=Spende.Art.SACH, datum__year=jahr)
        .exclude(bestaetigung__isnull=False, bestaetigung__storniert_am__isnull=True)
        .select_related("adresse"),
    })  # fmt: skip


def _pdf_link(liste) -> str:
    return reverse("spenden:pdf") + "?nummern=" + ",".join(str(b.nummer) for b in liste)


@require_POST
@rollen.recht_erforderlich("spenden.bestaetigen")
def ausstellen(request):
    jahr = _jahr(request)
    von = request.user.get_username()
    try:
        if request.POST.get("spende", "").isdigit():
            liste = [bst.sach_ausstellen(get_object_or_404(Spende, pk=request.POST["spende"]), von)]
        elif request.POST.get("adresse", "").isdigit():
            a = get_object_or_404(Adresse, pk=request.POST["adresse"])
            liste = [bst.geld_ausstellen(a, jahr, von)]
        else:
            liste = [bst.geld_ausstellen(a, jahr, von) for a, _, _ in bst.jahresliste(jahr)]
    except bst.BestaetigungsFehler as fehler:
        messages.error(request, str(fehler))
        return redirect(f"{reverse('spenden:bestaetigungen')}?jahr={jahr}")
    request.session["spenden_neu"] = _pdf_link(liste)
    endung = "en" if len(liste) != 1 else ""
    messages.success(request, f"{len(liste)} Zuwendungsbestätigung{endung} ausgestellt.")
    return redirect(f"{reverse('spenden:bestaetigungen')}?jahr={jahr}")


@rollen.recht_erforderlich("spenden.bestaetigen")
def pdf(request):
    nummern = [int(n) for n in request.GET.get("nummern", "").split(",") if n.isdigit()]
    liste = list(Zuwendungsbestaetigung.objects.filter(nummer__in=nummern).order_by("nummer"))
    if not liste:
        raise Http404
    name = f"zuwendungsbestaetigung-{liste[0].nummer}" + (
        f"-bis-{liste[-1].nummer}" if len(liste) > 1 else "")  # fmt: skip
    return pdf_antwort(bst.pdf(liste), f"{name}.pdf")


@require_POST
@rollen.recht_erforderlich("spenden.bestaetigen")
def stornieren(request, nummer):
    b = get_object_or_404(Zuwendungsbestaetigung, nummer=nummer)
    bst.stornieren(b, request.user.get_username())
    messages.success(request, f"Zuwendungsbestätigung Nr. {nummer} storniert. Die Spenden lassen "
                              "sich neu bestätigen.")  # fmt: skip
    return redirect(f"{reverse('spenden:bestaetigungen')}?jahr={b.ausgestellt_am.year}")


@never_cache
@rollen.recht_erforderlich("einstellungen.spenden")
def einstellungen(request):
    form = SpendenEinstellungenForm(request.POST or None, instance=SpendenEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("spenden:einstellungen")
    return render(request, "spenden/einstellungen.html", {"form": form})


# --- Dankesbriefe (ADR 0056) ---------------------------------------------------------------------


def _versand_vermerken(request, form, anzahl, art, danke):
    from apps.serienbriefe.models import Versand

    d = form.cleaned_data
    Versand.objects.create(
        von=request.user.get_username(), art=art, vorlage=d["vorlage"].name,
        betreff=d["vorlage"].betreff, anzahl=anzahl,
        auswahl=f"Dankesbriefe {d['jahr']} · {dict(danken.ARTEN)[d['art']]}"[:300],
        empfaenger=[f"a:{x.adresse.pk}" for x in danke],
    )  # fmt: skip


def _allgemein(jahr):
    from apps.serienbriefe.views import _allgemein as allgemein

    return allgemein(jahr)


@im_fenster
@never_cache
@rollen.recht_erforderlich("spenden.bestaetigen")
def dank(request):
    daten = request.POST or None
    form = DankForm(daten, jahre=_jahre(), initial={"jahr": _jahr(request)})
    kontext = {"form": form, "mail_bereit": mail.eingerichtet()}
    if not (request.method == "POST" and form.is_valid()):
        return render(request, "spenden/dank.html", kontext)
    d = form.cleaned_data
    danke = danken.auswahl(d["jahr"], d["art"], d["nur_offen"])
    per_mail = [x for x in danke if d["mail"] and x.per_mail]
    per_brief = [x for x in danke if x not in per_mail]
    schritt = request.POST.get("schritt", "vorschau")
    von = request.user.get_username()
    if schritt in ("pdf", "senden") and d["mit_bestaetigungen"]:
        fehler = danken.fehlende_ausstellen(per_brief if schritt == "pdf" else per_mail,
                                            d["jahr"], von)  # fmt: skip
        if fehler:
            for f in fehler[:5]:
                messages.error(request, f)
            return render(request, "spenden/dank.html", kontext | {"danke": danke})
    if schritt == "pdf" and per_brief:
        inhalt, warnungen = danken.briefe(per_brief, d["vorlage"], d["jahr"],
                                          d["mit_bestaetigungen"], d["mit_belegen"],
                                          _allgemein(d["jahr"]))  # fmt: skip
        danken.vermerken(per_brief, d["mit_belegen"])
        from apps.serienbriefe.models import Versand

        _versand_vermerken(request, form, len(per_brief), Versand.Art.BRIEF, per_brief)
        for w in warnungen[:10]:
            messages.warning(request, w)
        return pdf_antwort(inhalt, f"dankesbriefe-{d['jahr']}-{timezone.localdate():%Y-%m-%d}.pdf")
    if schritt == "senden" and per_mail:
        return _dank_senden(request, form, per_mail)
    kontext |= {"danke": danke, "per_mail": per_mail, "per_brief": per_brief, "d": d}
    return render(request, "spenden/dank.html", kontext)


@nicht_in_demo
def _dank_senden(request, form, per_mail):
    from apps.serienbriefe import gestaltung
    from apps.serienbriefe.models import Versand

    d = form.cleaned_data
    allgemein, gesendet, fehler = _allgemein(d["jahr"]), [], []
    for x in per_mail:
        e = danken.werte(x, d["jahr"])
        anhaenge = [
            (n, inhalt, "application/pdf")
            for n, inhalt in danken.anlagen(x, d["mit_bestaetigungen"], d["mit_belegen"])
        ]
        try:
            betreff, text, html = gestaltung.mail(d["vorlage"], e, allgemein)
            mail.senden(betreff, text, [x.adresse.email], html=html, anhaenge=anhaenge)
        except mail.MailFehler as grund:
            fehler.append(f"{x.adresse.name}: {grund}")
            if len(fehler) >= 3 and not gesendet:
                break
        else:
            gesendet.append(x)
    if gesendet:
        danken.vermerken(gesendet, d["mit_belegen"])
        _versand_vermerken(request, form, len(gesendet), Versand.Art.EMAIL, gesendet)
        n = len(gesendet)
        messages.success(request, f"{n} Dankesbrief{'e' if n != 1 else ''} per E-Mail gesendet. "
                                  "Die übrigen jetzt als PDF erstellen.")  # fmt: skip
    for f in fehler[:10]:
        messages.error(request, f"Nicht gesendet: {f}")
    return render(request, "spenden/dank.html", {"form": form, "mail_bereit": True})


@never_cache
@rollen.recht_erforderlich("spenden.bestaetigen")
def belege(request):
    """Belege aus anderen Programmen hochladen und Spendern zuordnen."""
    jahr = _jahr(request)
    von = request.user.get_username()
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "hochladen":
            dateien = request.FILES.getlist("dateien")
            zugeordnet, offen = 0, 0
            for datei in dateien[:200]:
                try:
                    b = danken.hochladen(datei, jahr, von)
                except privatdateien.DateiFehler as fehler:
                    messages.error(request, f"{datei.name}: {fehler}")
                    continue
                zugeordnet, offen = (
                    (zugeordnet + 1, offen) if b.adresse_id else (zugeordnet, offen + 1)
                )
            if zugeordnet or offen:
                messages.success(request, f"{zugeordnet} Beleg(e) über die Belegnummer zugeordnet, "
                                          f"{offen} bitte von Hand zuordnen.")  # fmt: skip
        elif aktion == "zuordnen":
            b = get_object_or_404(SpendenBeleg, pk=request.POST.get("beleg"))
            adresse = Adresse.objects.filter(pk=request.POST.get("adresse") or 0).first()
            if adresse:
                b.adresse, b.spende = adresse, None
                b.save(update_fields=["adresse", "spende"])
                messages.success(request, f"„{b.dateiname}“ {adresse.name} zugeordnet.")
        elif aktion == "loeschen":
            b = get_object_or_404(SpendenBeleg, pk=request.POST.get("beleg"))
            papierkorb.loeschen(request.user, "Spendenbeleg", b.dateiname, b,
                                recht="spenden.bestaetigen")  # fmt: skip
            messages.success(request, f"„{b.dateiname}“ in den Papierkorb gelegt.")
        return redirect(f"{reverse('spenden:belege')}?jahr={jahr}")
    spender = Adresse.objects.filter(spenden__datum__year=jahr).distinct().order_by(
        "organisation", "nachname")  # fmt: skip
    return render(request, "spenden/belege.html", {
        "jahr": jahr, "jahre": _jahre(), "spender": spender,
        "offen": SpendenBeleg.objects.filter(adresse__isnull=True),
        "zugeordnet": SpendenBeleg.objects.filter(adresse__isnull=False, jahr=jahr)
        .select_related("adresse", "spende"),
    })  # fmt: skip


@never_cache
@rollen.recht_erforderlich("spenden.bestaetigen")
def beleg(request, pk):
    b = get_object_or_404(SpendenBeleg, pk=pk)
    inhalt = privatdateien.lesen(SpendenBeleg.ORDNER, b.datei)
    if inhalt is None:
        raise Http404("Datei nicht mehr lesbar.")
    return pdf_antwort(inhalt, danken._dateiname(b.dateiname))
