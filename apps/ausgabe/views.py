"""Einlass: Kundennummer scannen, Ampel sehen, Abholung eintragen. Dazu die Kasse."""

import datetime as dt
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Concat
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.ausgabe import ampel, kasse, konto, korrekturen, sonderaktionen
from apps.ausgabe import stelle as stelle_wahl
from apps.ausgabe.forms import AusgabeEinstellungenForm
from apps.ausgabe.models import (
    AusgabeEinstellungen,
    BeitragsfreierZeitraum,
    Buchung,
    Sonderaktion,
    Teilnahme,
)
from apps.core import module
from apps.core.auswahl import KORREKTURGRUENDE
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden import merkmale, werte, zugang
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Haushalt,
    KundenEinstellungen,
    Notiz,
    Person,
    Zugriff,
)
from apps.kunden.views import notiz_schreiben, notizen_kontext

LETZTE_ABHOLUNGEN = 5


def _stelle(request):
    return stelle_wahl.aktuelle(request.user)


LETZTE_KUNDEN = 20


def _letzte(request, stelle) -> list[dict]:
    """Die letzten Kunden des Tages am Einlass: hier aufgerufene (Zugriffe dieses Kontos) und an
    der Ausgabestelle eingetragene Abholungen, neueste zuerst, je Kundennummer einmal."""
    heute = timezone.localdate()
    eintraege: dict[str, dict] = {}

    def merken(nummer, zeit, abgeholt):
        e = eintraege.setdefault(nummer, {"nummer": nummer, "zeit": zeit, "abgeholt": False})
        e["zeit"] = max(e["zeit"], zeit)
        e["abgeholt"] = e["abgeholt"] or abgeholt

    abholungen = Abholung.objects.filter(datum=heute, erfasst_am__isnull=False)
    abholungen = (abholungen.filter(ausgabestelle=stelle) if stelle
                  else abholungen.filter(eingetragen_von=_benutzername(request.user)))  # fmt: skip
    for nummer, zeit in abholungen.order_by("-erfasst_am").values_list(
            "haushalt__kundennummer", "erfasst_am")[:LETZTE_KUNDEN]:  # fmt: skip
        merken(nummer, zeit, True)
    zugriffe = Zugriff.objects.filter(benutzer=request.user, export=False, zeitpunkt__date=heute)
    for nummer, zeit in zugriffe.order_by("-zeitpunkt").values_list(
            "kundennummer", "zeitpunkt")[:LETZTE_KUNDEN * 3]:  # fmt: skip
        merken(nummer, zeit, False)
    liste = sorted(eintraege.values(), key=lambda e: e["zeit"], reverse=True)[:LETZTE_KUNDEN]
    hauptperson = Person.objects.filter(haushalt=OuterRef("pk"), ist_hauptperson=True)
    namen = dict(
        zugang.filtern(Haushalt.objects, request.user)
        .filter(kundennummer__in=[e["nummer"] for e in liste])
        .annotate(n=Subquery(hauptperson.values("nachname")[:1]),
                  v=Subquery(hauptperson.values("vorname")[:1]))
        .values_list("kundennummer", Concat("v", Value(" "), "n"))
    )  # fmt: skip
    return [{**e, "name": (namen[e["nummer"]] or "").strip()} for e in liste
            if e["nummer"] in namen]  # fmt: skip


def _suche_kontext(request) -> dict:
    stelle = _stelle(request)
    return {"stelle": stelle, "letzte": _letzte(request, stelle)}


def _finden(eingabe: str):
    """Kundennummer wie gescannt; Ziffern auch ohne bzw. mit führenden Nullen."""
    eingabe = eingabe.strip()
    haushalte = Haushalt.objects.select_related("kundengruppe__ausgabestelle")
    treffer = haushalte.filter(kundennummer__iexact=eingabe).first()
    if treffer is None and eingabe.isdigit():
        treffer = haushalte.filter(kundennummer__regex=rf"^0*{int(eingabe)}$").first()
    return treffer


def _benutzername(user) -> str:
    return (user.get_full_name() or user.get_username())[:100]


def _ergebnis(request, h, meldung=None):
    """Kontext für die Ampel-Karte eines Haushalts."""
    heute = timezone.localdate()
    einstellungen = AusgabeEinstellungen.laden()
    h = (
        Haushalt.objects.select_related("kundengruppe__ausgabestelle")
        .prefetch_related(
            "personen", "abholer", "sperren", "ausnahmen", "abholungen__ausgabestelle"
        )
        .get(pk=h.pk)
    )
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    erwachsene, kinder = h.groesse(kind_bis, heute)
    hinweise = module.einlass_hinweise(h, heute, _stelle(request))
    bewertung = ampel.modul_hinweise_beachten(
        ampel.bewerten(h, heute, _stelle(request), einstellungen), hinweise
    )
    abholungen = list(h.abholungen.all())
    beitrag = einstellungen.beitrag_fuer(h, heute, kind_bis)
    regulaer = einstellungen.beitrag_fuer(h, heute, kind_bis, frei_beachten=False)
    vorschlaege, vorschlag_hinweis = konto.vorschlaege(h, heute, einstellungen, regulaer)
    merkmale_zeilen, merkmale_art9 = merkmale.einlass(h, request.user)
    from apps.kunden import krankmeldung

    return {
        "krank": krankmeldung.aktuelle(h.kundennummer, heute),
        "merkmale": merkmale_zeilen,
        "merkmale_art9": merkmale_art9,
        "h": h,
        "hauptperson": next((p for p in h.personen.all() if p.ist_hauptperson), None),
        "personen": sorted(h.personen.all(), key=lambda p: not p.ist_hauptperson),
        "erwachsene": erwachsene,
        "kinder": kinder,
        "bewertung": bewertung,
        "beitrag": beitrag,
        "beitragsfrei": BeitragsfreierZeitraum.am(heute),
        "bar_vorschlag": konto.bar_vorschlag(beitrag, h.kontostand),
        "vorschlaege": vorschlaege,
        "vorschlag_hinweis": vorschlag_hinweis,
        "einzahlungen_heute": h.buchungen.filter(art=Buchung.Art.EINZAHLUNG, datum=heute),
        "einstellungen": einstellungen,
        "abholungen": abholungen[:LETZTE_ABHOLUNGEN],
        "heute_erfasst": [a for a in abholungen if a.datum == heute and a.erfasst_am],
        "darf_ausnahme": rollen.hat_recht(request.user, "einlass.ausnahme"),
        **notizen_kontext(h.kundennummer, request.user),
        "sonderaktionen": sonderaktionen.fuer_haushalt(h, heute, erwachsene, kinder),
        "darf_zuruecknehmen": rollen.hat_recht(request.user, "einlass.zuruecknehmen"),
        "korrektur_offen": korrekturen.offene(h.kundennummer),
        "korrekturen_entschieden": korrekturen.entschiedene(h.kundennummer),
        "korrektur_tage": korrekturen.TAGE_ANZEIGEN,
        "korrekturgruende": KORREKTURGRUENDE,
        "heute": heute,
        "meldung": meldung,
        "modul_hinweise": hinweise,
    }


def _antworten(request, kontext):
    if request.headers.get("HX-Request"):
        # Fortschritt in der Kopfzeile gleich mit austauschen (hx-swap-oob)
        return render(request, "ausgabe/_einlass.html", {**kontext, "fortschritt_oob": True})
    return render(request, "ausgabe/empfang.html", kontext)


@rollen.recht_erforderlich("einlass.nutzen")
def empfang(request):
    konto.buchungsfristen_anwenden()
    nummer = request.GET.get("nummer", "").strip()
    kontext = {"stelle": _stelle(request)} if nummer else _suche_kontext(request)
    if nummer:
        h = _finden(nummer)
        grund = zugang.sperrgrund(request.user, h) if h else ""
        if h is None:
            kontext["nicht_gefunden"] = nummer
        elif grund:
            kontext["nicht_erlaubt"] = grund
            kontext["fremd_nummer"] = h.kundennummer
        else:
            kontext.update(_ergebnis(request, h))
            Zugriff.objects.create(
                benutzer=request.user,
                benutzername=request.user.get_username(),
                kundennummer=h.kundennummer,
                besondere_kategorie=kontext["merkmale_art9"],
            )
    return _antworten(request, kontext)


@require_POST
@rollen.recht_erforderlich("einlass.nutzen")
def ausgabestelle_waehlen(request):
    """Auswahlfeld oben im Menü (ADR 0067): gilt bis zur nächsten Wahl, auch nach dem Abmelden."""
    stelle_wahl.waehlen(request.user, request.POST.get("ausgabestelle", ""))
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}):
        weiter = reverse("ausgabe:empfang")
    return redirect(weiter)


def _gemeldet(antwort):
    """Ereignis für die Seite: Am Einlass hat sich etwas geändert (z. B. Abholung eingetragen).
    Wer darauf hört (etwa der Aufruf-Kasten unter dem Menü), lädt sich sofort neu."""
    antwort["HX-Trigger"] = "einlassGeaendert"
    return antwort


def _zurueck(request, h, text, stufe=messages.SUCCESS):
    """Nach einer Aktion: HTMX bekommt die aktualisierte Karte, sonst Weiterleitung."""
    if request.headers.get("HX-Request"):
        kontext = {"stelle": _stelle(request), **_ergebnis(request, h, meldung=text)}
        return _gemeldet(render(request, "ausgabe/_einlass.html",
                                {**kontext, "fortschritt_oob": True}))  # fmt: skip
    messages.add_message(request, stufe, text)
    return redirect(f"{reverse('ausgabe:empfang')}?nummer={h.kundennummer}")


def _zur_suche(request, h, text):
    """Nach dem Anmelden eines Kunden: zurück zum Suchfeld für den nächsten Kunden."""
    text = f"Kunde {h.kundennummer}: {text}"
    if request.headers.get("HX-Request"):
        kontext = {**_suche_kontext(request), "meldung": text, "fertig": h.kundennummer}
        return _gemeldet(render(request, "ausgabe/_einlass.html",
                                {**kontext, "fortschritt_oob": True}))  # fmt: skip
    messages.success(request, text)
    return redirect("ausgabe:empfang")


@require_POST
@rollen.recht_erforderlich("einlass.abholung")
def abholung_eintragen(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    kontext = _ergebnis(request, h)
    if not kontext["bewertung"].darf_abholen:
        return _zurueck(request, h, "Nicht eingetragen: Die Ampel steht auf Rot.", messages.ERROR)
    try:
        beitrag = werte.betrag(request.POST.get("beitrag", ""))
    except werte.UngueltigerWert:
        return _zurueck(request, h, "Nicht eingetragen: Beitrag ist kein Betrag.", messages.ERROR)
    beitrag = kontext["beitrag"] if beitrag is None else beitrag
    if beitrag < 0:
        return _zurueck(request, h, "Nicht eingetragen: Beitrag ist negativ.", messages.ERROR)
    try:
        bar = werte.betrag(request.POST.get("bar", ""))
    except werte.UngueltigerWert:
        return _zurueck(
            request, h, "Nicht eingetragen: Bar gezahlt ist kein Betrag.", messages.ERROR
        )
    jetzt = timezone.localtime()
    stelle = _stelle(request)
    try:
        with transaction.atomic():
            abholung = Abholung.objects.create(
                haushalt=h,
                datum=jetzt.date(),
                uhrzeit=jetzt.time().replace(second=0, microsecond=0),
                beitrag=beitrag,
                ausgabestelle=stelle,
                eingetragen_von=_benutzername(request.user),
                erfasst_am=timezone.now(),
            )
            zahlung = konto.abholung_buchen(
                abholung,
                beitrag,
                bar,
                kontext["einstellungen"],
                stelle,
                _benutzername(request.user),
            )
            Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=jetzt.date())
    except konto.KontoFehler as fehler:
        return _zurueck(request, h, f"Nicht eingetragen: {fehler}", messages.ERROR)
    teile = [f"Abholung eingetragen. Bar erhalten: {konto.euro(zahlung.bar)}"]
    if zahlung.vom_konto:
        teile.append(f"{konto.euro(zahlung.vom_konto)} aus Guthaben")
    if zahlung.angeschrieben:
        teile.append(f"{konto.euro(zahlung.angeschrieben)} angeschrieben")
    if zahlung.gutgeschrieben:
        teile.append(f"{konto.euro(zahlung.gutgeschrieben)} als Guthaben gebucht")
    text = f"{', '.join(teile)}. Kontostand jetzt: {konto.euro(zahlung.kontostand)}."
    return _zur_suche(request, h, text)


@require_POST
@rollen.recht_erforderlich("einlass.zuruecknehmen")
def abholung_zuruecknehmen(request, pk):
    """Nimmt eine Abholung zurück, auch an späteren Tagen (nur mit eigenem Recht, ADR 0035)."""
    abholung = get_object_or_404(Abholung.objects.select_related("haushalt"), pk=pk)
    h = zugang.haushalt(request.user, abholung.haushalt.kundennummer)
    korrekturen.zuruecknehmen(korrekturen.Art.ABHOLUNG, abholung)
    h.refresh_from_db()
    return _zurueck(
        request,
        h,
        f"Abholung zurückgenommen. Kontostand jetzt: {konto.euro(h.kontostand or 0)}.",
    )


@require_POST
@rollen.recht_erforderlich("einlass.nutzen")
def korrektur_beantragen(request, art, pk):
    """Ohne Recht zum Zurücknehmen: Bitte an Admin oder berechtigte Rolle (ADR 0035)."""
    if art not in korrekturen.Art.values:
        raise Http404
    obj = korrekturen._objekt(art, pk)
    if obj is None:
        raise Http404
    nummer = obj.kundennummer if hasattr(obj, "kundennummer") and obj.kundennummer else (
        obj.haushalt.kundennummer)  # fmt: skip
    h = zugang.haushalt(request.user, nummer)
    try:
        korrekturen.beantragen(
            art, pk, grund=request.POST.get("grund", ""),
            anmerkung=request.POST.get("anmerkung", ""), von=_benutzername(request.user),
        )  # fmt: skip
    except korrekturen.KorrekturFehler as fehler:
        return _zurueck(request, h, f"Nicht gesendet: {fehler}", messages.ERROR)
    return _zurueck(
        request, h, "Korrekturwunsch gesendet. Ein Admin bzw. das Büro entscheidet darüber."
    )


@require_POST
@rollen.recht_erforderlich("einlass.sonderaktion")
def sonderaktion_eintragen(request, kundennummer, aktion):
    h = zugang.haushalt(request.user, kundennummer)
    a = get_object_or_404(Sonderaktion, pk=aktion)
    auswahl = a.auswahl.filter(pk=request.POST.get("auswahl") or None).first()
    erwachsene, kinder = h.groesse(KundenEinstellungen.laden().kind_bis_alter)
    try:
        t = sonderaktionen.eintragen(
            a, h, auswahl=auswahl, erwachsene=erwachsene, kinder=kinder,
            stelle=_stelle(request), von=_benutzername(request.user),
        )  # fmt: skip
    except sonderaktionen.SonderaktionFehler as fehler:
        return _zurueck(request, h, f"Nicht eingetragen: {fehler}", messages.ERROR)
    was = f" ({t.auswahl})" if t.auswahl else ""
    return _zurueck(request, h, f"{a}{was} eingetragen: {t.menge}×.")


@require_POST
@rollen.recht_erforderlich("einlass.zuruecknehmen")
def teilnahme_zuruecknehmen(request, pk):
    t = get_object_or_404(Teilnahme, pk=pk)
    h = zugang.haushalt(request.user, t.kundennummer)
    korrekturen.zuruecknehmen(korrekturen.Art.TEILNAHME, t)
    return _zurueck(request, h, f"{t.aktion} zurückgenommen.")


@require_POST
@rollen.recht_erforderlich("einlass.zahlung")
def einzahlung(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    try:
        betrag = werte.betrag(request.POST.get("betrag", ""))
        konto.einzahlen(
            h,
            betrag,
            _stelle(request),
            _benutzername(request.user),
            request.POST.get("bemerkung", "").strip(),
        )
    except (werte.UngueltigerWert, konto.KontoFehler):
        return _zurueck(
            request, h, "Nicht gebucht: Bitte einen Betrag größer als 0 angeben.", messages.ERROR
        )
    h.refresh_from_db()
    return _zurueck(
        request,
        h,
        f"Einzahlung von {konto.euro(betrag)} gebucht. Bar erhalten: {konto.euro(betrag)}. "
        f"Kontostand jetzt: {konto.euro(h.kontostand)}.",
    )


@require_POST
@rollen.recht_erforderlich("einlass.zuruecknehmen")
def einzahlung_zuruecknehmen(request, pk):
    """Nimmt eine Einzahlung zurück, auch an späteren Tagen (nur mit eigenem Recht)."""
    buchung = get_object_or_404(Buchung, pk=pk, art=Buchung.Art.EINZAHLUNG, haushalt__isnull=False)
    h = zugang.haushalt(request.user, buchung.haushalt.kundennummer)
    korrekturen.zuruecknehmen(korrekturen.Art.ZAHLUNG, buchung)
    h.refresh_from_db()
    return _zurueck(
        request,
        h,
        f"Zahlung zurückgenommen. Kontostand jetzt: {konto.euro(h.kontostand or 0)}.",
    )


@require_POST
@rollen.recht_erforderlich("konto.korrektur")
def korrektur(request, kundennummer):
    """Korrekturbuchung ohne Bargeld, von der Haushaltsseite aus."""
    h = zugang.haushalt(request.user, kundennummer)
    try:
        betrag = werte.betrag(request.POST.get("betrag", ""))
        konto.korrigieren(
            h, betrag, request.POST.get("begruendung", ""), _benutzername(request.user)
        )
    except (werte.UngueltigerWert, konto.KontoFehler) as fehler:
        text = str(fehler) if isinstance(fehler, konto.KontoFehler) else "Kein gültiger Betrag."
        messages.error(request, f"Nicht gebucht: {text}")
    else:
        messages.success(request, "Korrektur gebucht.")
    return redirect("kunden:haushalt", kundennummer=h.kundennummer)


@require_POST
@rollen.recht_erforderlich("einlass.ausnahme")
def ausnahme_erteilen(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    begruendung = request.POST.get("begruendung", "").strip()
    if not begruendung:
        return _zurueck(request, h, "Bitte eine Begründung angeben.", messages.ERROR)
    Ausnahme.objects.create(
        haushalt=h,
        datum=timezone.localdate(),
        begruendung=begruendung,
        eingetragen_von=_benutzername(request.user),
        erfasst_am=timezone.now(),
    )
    return _zurueck(request, h, "Ausnahme für heute erteilt.")


def _datum(text, muster, ersatz):
    try:
        return dt.datetime.strptime(text, muster).date()
    except (TypeError, ValueError):
        return ersatz


def _monat_verschieben(tag: dt.date, monate: int) -> dt.date:
    index = tag.year * 12 + tag.month - 1 + monate
    return dt.date(index // 12, index % 12 + 1, 1)


@rollen.recht_erforderlich("kasse.sehen")
def kasse_ansehen(request):
    """Kasse nach Tag (je Ausgabestelle), Monat (je Tag) oder Jahr (je Monat), rückwirkend."""
    heute = timezone.localdate()
    ansicht = request.GET.get("ansicht", "tag")
    stellen = Ausgabestelle.objects.order_by("name")
    stelle_pk = request.GET.get("stelle", "")
    stelle = stellen.filter(pk=stelle_pk).first() if stelle_pk.isdigit() else None
    buchungen = Buchung.objects.all()
    if stelle:
        buchungen = buchungen.filter(ausgabestelle=stelle)

    if ansicht == "jahr":
        jahr = int(request.GET["jahr"]) if request.GET.get("jahr", "").isdigit() else heute.year
        jahr = min(max(jahr, 2000), 2100)
        beginn = dt.date(jahr, 1, 1)
        buchungen = buchungen.filter(datum__year=jahr)
        zeilen = kasse.nach_monat(buchungen)
        titel = f"Jahr {jahr}"
        zurueck, vor, aktuell = {"jahr": jahr - 1}, {"jahr": jahr + 1}, {"jahr": jahr}
    elif ansicht == "monat":
        beginn = _datum(request.GET.get("monat"), "%Y-%m", heute).replace(day=1)
        buchungen = buchungen.filter(datum__year=beginn.year, datum__month=beginn.month)
        zeilen = kasse.nach_tag(buchungen)
        titel = f"{konto.MONATE[beginn.month - 1]} {beginn.year}"
        zurueck = {"monat": f"{_monat_verschieben(beginn, -1):%Y-%m}"}
        vor = {"monat": f"{_monat_verschieben(beginn, 1):%Y-%m}"}
        aktuell = {"monat": f"{beginn:%Y-%m}"}
    else:
        ansicht = "tag"
        beginn = _datum(request.GET.get("datum"), "%Y-%m-%d", heute)
        buchungen = buchungen.filter(datum=beginn)
        zeilen = kasse.nach_ausgabestelle(buchungen)
        titel = f"{ampel.WOCHENTAGE[beginn.weekday()]} {beginn:%d.%m.%Y}"
        zurueck = {"datum": f"{beginn - dt.timedelta(days=1):%Y-%m-%d}"}
        vor = {"datum": f"{beginn + dt.timedelta(days=1):%Y-%m-%d}"}
        aktuell = {"datum": f"{beginn:%Y-%m-%d}"}

    einzeln = rollen.hat_recht(request.user, "kasse.einzelbuchungen")
    filter_stelle = {"stelle": stelle.pk} if stelle else {}

    def zeile(z):
        """Titel der Zeile und gegebenenfalls Link auf die feinere Ansicht."""
        g = z["gruppe"]
        if ansicht == "jahr":
            titel = konto.MONATE[g.month - 1]
            link = urlencode({"ansicht": "monat", "monat": f"{g:%Y-%m}", **filter_stelle})
        elif ansicht == "monat":
            titel, link = (
                f"{ampel.WOCHENTAGE[g.weekday()]} {g:%d.%m.}",
                urlencode({"ansicht": "tag", "datum": f"{g:%Y-%m-%d}", **filter_stelle}),
            )
        else:
            titel, link = g or "ohne Ausgabestelle", None
        return {"titel": titel, "link": link, "werte": werte(z)}

    def werte(z):
        """(Bezeichnung, Wert, ist Betrag) je Spalte."""
        return [(name, z[k], k != "abholungen") for k, name in kasse.SPALTEN]

    summe = kasse.summe(buchungen)
    # Einzelbuchungen mit Kundennummer nur mit eigenem Recht, nur in der Tagesansicht.
    einzelbuchungen = (
        buchungen.select_related("ausgabestelle").order_by("zeitpunkt")
        if einzeln and ansicht == "tag"
        else None
    )
    if request.GET.get("format") == "pdf":
        inhalt = kasse.bericht_pdf(
            ansicht, titel, stelle, [zeile(z) for z in zeilen], werte(summe), einzelbuchungen
        )
        return pdf_antwort(inhalt, f"kasse-{ansicht}-{beginn:%Y-%m-%d}.pdf")
    return render(
        request,
        "ausgabe/kasse.html",
        {
            "ansicht": ansicht,
            "titel": titel,
            "beginn": beginn,
            "zeilen": [zeile(z) for z in zeilen],
            "summe": werte(summe),
            "bar_gesamt": summe["bar_gesamt"],
            "spalten": kasse.SPALTEN,
            "stellen": stellen,
            "stelle": stelle,
            "zurueck": urlencode({"ansicht": ansicht, **zurueck, **filter_stelle}),
            "vor": urlencode({"ansicht": ansicht, **vor, **filter_stelle}),
            "einzelbuchungen": einzelbuchungen,
            "pdf": urlencode({"ansicht": ansicht, **aktuell, **filter_stelle, "format": "pdf"}),
        },
    )


@rollen.recht_erforderlich("einstellungen.ausgabe")
def einstellungen(request):
    form = AusgabeEinstellungenForm(request.POST or None, instance=AusgabeEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen der Ausgabe gespeichert.")
        return redirect("ausgabe:einstellungen")
    return render(request, "ausgabe/einstellungen.html", {"form": form})


@require_POST
@rollen.recht_erforderlich("kunden.notizen")
def notiz(request, kundennummer):
    h = zugang.haushalt(request.user, kundennummer)
    if notiz_schreiben(h, request.POST.get("text", ""), request.user) is None:
        return _zurueck(request, h, "Bitte einen Text für die Notiz eingeben.", messages.ERROR)
    return _zurueck(request, h, "Notiz gespeichert.")


@require_POST
@rollen.recht_erforderlich("kunden.notizen")
def krank(request, kundennummer):
    from apps.kunden.krankmeldung import Fehler
    from apps.kunden.views import krank_aus_formular

    h = zugang.haushalt(request.user, kundennummer)
    try:
        return _zurueck(request, h, krank_aus_formular(h, request))
    except Fehler as f:
        return _zurueck(request, h, str(f), messages.ERROR)


@require_POST
@rollen.recht_erforderlich("kunden.notizen")
def notiz_loeschen(request, pk):
    notiz = get_object_or_404(Notiz, pk=pk)
    h = zugang.haushalt(request.user, notiz.kundennummer)
    if not notiz.darf_loeschen(request.user):
        return _zurueck(
            request, h, "Diese Notiz dürfen nur Büro und Admin löschen.", messages.ERROR
        )
    from apps.kunden.views import _notiz_in_papierkorb

    _notiz_in_papierkorb(request.user, notiz)
    return _zurueck(request, h, "Notiz in den Papierkorb gelegt.")
