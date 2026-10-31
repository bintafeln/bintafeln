"""Seiten des Dienstplans (ADR 0077); Regeln in ``apps/dienstplan/plan.py``."""

import datetime as dt

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.adressen.models import Adresse
from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import papierkorb, whatsapp
from apps.core.pdf import pdf_antwort
from apps.dienstplan import plan
from apps.dienstplan.forms import (
    AufgabeForm,
    AusfallForm,
    DiensttagForm,
    EinstellungenForm,
    StelleForm,
    helfer_aktiv,
)
from apps.dienstplan.models import (
    Aufgabe,
    Ausfall,
    Besetzung,
    DienstplanEinstellungen,
    DienstStelle,
    Diensttag,
)
from apps.konten import rollen
from apps.konten.views import nicht_in_demo
from apps.kunden.models import Ausgabestelle

sehen = rollen.recht_erforderlich("dienstplan.sehen")
planen = rollen.recht_erforderlich("dienstplan.planen")
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]  # fmt: skip
TAGNAME = dict(zip(WOCHENTAGE, ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                                "Samstag", "Sonntag"], strict=True))  # fmt: skip


def _monat(daten) -> dt.date:
    text = (f"{daten['jahr']}-{daten['m']}" if daten.get("jahr") and daten.get("m")
            else daten.get("monat"))  # fmt: skip
    try:
        return dt.datetime.strptime(text or "", "%Y-%m").date()
    except ValueError:
        return timezone.localdate().replace(day=1)


def _verschieben(erster: dt.date, monate: int) -> dt.date:
    jahr, monat = divmod(erster.year * 12 + erster.month - 1 + monate, 12)
    return dt.date(jahr, monat + 1, 1)


def _letzter(erster: dt.date) -> dt.date:
    return _verschieben(erster, 1) - dt.timedelta(days=1)


def _stelle_waehlen(request, stellen):
    """Gewählte Stelle (?stelle=), sonst die Ausgabestelle aus dem Menü, sonst die erste."""
    from apps.ausgabe.stelle import aktuelle

    wahl = request.GET.get("stelle")
    if not wahl and (a := aktuelle(request.user)) is not None:
        wahl = str(a.pk)
    return next((s for s in stellen if str(s.ausgabestelle_id) == wahl), stellen[0])


def _naechster_tag(stelle, tage) -> str:
    """Ohne Wahl: der nächste Ausgabetag ab heute, an dem es Aufgaben gibt."""
    mit = [t for t in tage if stelle.aufgaben.filter(wochentag=t).exists()] or tage
    if not mit:
        return ""
    heute = timezone.localdate().weekday()
    return min(mit, key=lambda t: (WOCHENTAGE.index(t) - heute) % 7)


def _link(stelle, tag, erster) -> str:
    return (f"{reverse('dienstplan:plan')}?stelle={stelle.ausgabestelle_id}&tag={tag}"
            f"&monat={erster:%Y-%m}")  # fmt: skip


@never_cache
@sehen
def uebersicht(request):
    """Plan wie auf Papier: eine Ausgabestelle, ein Wochentag, ein Monat."""
    stellen = list(plan.stellen())
    if not stellen:
        return render(request, "dienstplan/plan.html", {"keine_stelle": True,
                      "planen": rollen.hat_recht(request.user, "dienstplan.planen")})  # fmt: skip
    stelle = _stelle_waehlen(request, stellen)
    tage = wochentage(stelle.tage)
    tag = request.GET.get("tag") if request.GET.get("tag") in tage else _naechster_tag(stelle, tage)
    erster = _monat(request.GET)
    daten, zeilen = plan.monat(stelle, tag, erster, _letzter(erster)) if tag else ([], [])
    jahr = timezone.localdate().year
    return render(request, "dienstplan/plan.html", {
        "stellen": stellen, "stelle": stelle, "tage": tage, "tag": tag,
        "tagname": TAGNAME.get(tag, ""), "daten": daten, "zeilen": zeilen,
        "titel": f"{MONATE[erster.month - 1]} {erster.year}", "monat": f"{erster:%Y-%m}",
        "erster": erster, "monate": list(enumerate(MONATE, start=1)),
        "jahre": range(min(jahr - 2, erster.year), max(jahr + 1, erster.year) + 1),
        "vorher": f"{_verschieben(erster, -1):%Y-%m}",
        "nachher": f"{_verschieben(erster, 1):%Y-%m}",
        "heute": timezone.localdate(),
        "planen": rollen.hat_recht(request.user, "dienstplan.planen"),
        "darf_melden": plan.darf_selbst_melden(request.user),
        "ich": plan.helfer_von(request.user),
        "offen": sum(p.fehlt for _, ps in zeilen for p in ps),
        "diensttag": Diensttag.objects.filter(stelle=stelle, wochentag=tag).first(),
        **_karten(daten, zeilen),
    })  # fmt: skip


def _karten(daten, zeilen) -> dict:
    """Derselbe Plan für schmale Bildschirme: eine Karte je Datum, gleichnamige Aufgaben
    zusammen (z. B. „Obst“ mit vier Namen). Aufgeklappt ist der nächste Ausgabetag; vergangene
    Tage stehen eingeklappt unter „Frühere Tage“."""
    heute = timezone.localdate()
    naechster = next((d for d in daten if d >= heute), None)
    karten = []
    for i, datum in enumerate(daten):
        gruppen = []
        for a, plaetze in zeilen:
            if gruppen and (gruppen[-1]["name"], gruppen[-1]["zeit"]) == (a.name, a.zeit):
                gruppen[-1]["plaetze"].append(plaetze[i])
            else:
                gruppen.append({"name": a.name, "zeit": a.zeit, "plaetze": [plaetze[i]]})
        karten.append({"datum": datum, "gruppen": gruppen, "offen": datum == naechster,
                       "fehlen": sum(ps[i].fehlt for _, ps in zeilen)})  # fmt: skip
    return {"karten_frueher": [k for k in karten if k["datum"] < heute],
            "karten": [k for k in karten if k["datum"] >= heute]}  # fmt: skip


@never_cache
@sehen
def plan_pdf(request):
    """A4 quer zum Aushängen: eine Seite je Wochentag der Stelle (oder nur der gewählte)."""
    from apps.dienstplan import pdf

    stelle = get_object_or_404(plan.stellen(), ausgabestelle_id=request.GET.get("stelle"))
    erster = _monat(request.GET)
    tage = wochentage(stelle.tage)
    if request.GET.get("tag") in tage:
        tage = [request.GET["tag"]]
    seiten = []
    for tag in tage:
        daten, zeilen = plan.monat(stelle, tag, erster, _letzter(erster))
        seiten.append(
            (
                TAGNAME[tag],
                daten,
                zeilen,
                Diensttag.objects.filter(stelle=stelle, wochentag=tag).first(),
            )
        )
    inhalt = pdf.monat(stelle, MONATE[erster.month - 1], erster.year, seiten)
    return pdf_antwort(inhalt, f"dienstplan-{erster:%Y-%m}.pdf")


@never_cache
@planen
def platz(request, datum, aufgabe):
    """Ausfall ohne Ersatz melden, Ersatz oder Gast eintragen, zurücknehmen."""
    try:
        tag = dt.date.fromisoformat(datum)
    except ValueError as fehler:
        raise Http404 from fehler
    a = get_object_or_404(Aufgabe.objects.select_related("stelle__ausgabestelle"), pk=aufgabe,
                          stelle__aktiv=True)  # fmt: skip
    if tag not in plan.ausgabetage(a.stelle, tag, tag, a.wochentag):
        raise Http404
    zurueck = _link(a.stelle, a.wochentag, tag.replace(day=1))
    frei = plan.verfuegbar(tag)
    if request.method == "POST":
        wahl, gast = request.POST.get("helfer", ""), request.POST.get("gast", "").strip()
        neu = (get_object_or_404(Adresse, pk=wahl, helfer=True, helfer_aktiv=True)
               if wahl else None)  # fmt: skip
        if neu is not None and neu not in frei:
            messages.error(request, f"{neu} kann am {tag:%d.%m.%Y} nicht einspringen "
                                    "(Ausfall gemeldet oder schon eingeteilt).")  # fmt: skip
            return redirect(request.path)
        plan.ersatz_eintragen(tag, a, neu, request.user.get_username(), gast=gast)
        text = (
            f"{neu} springt ein."
            if neu
            else (f"Gast „{gast}“ hilft mit." if gast else "Eintrag zurückgenommen.")
        )
        messages.success(request, f"{tag:%d.%m.%Y}, {a}: {text}")
        return redirect(zurueck)
    p_ = plan.platz(tag, a)
    nachricht = (f"Hallo {p_.wer.vorname or p_.wer.name}, es geht um den Dienst am "
                 f"{tag:%d.%m.%Y}: {a.stelle}, {a}.") if p_.wer else ""  # fmt: skip
    return render(request, "dienstplan/platz.html", {
        "p": p_, "frei": frei, "zurueck": zurueck,
        "tagname": TAGNAME[a.wochentag], "ausfall_form": AusfallForm(planen=True),
        "whatsapp": whatsapp.fuer_person(p_.wer, nachricht),
    })  # fmt: skip


@never_cache
@sehen
def meine(request):
    """Eigene Dienste der nächsten vier Wochen und eigene Ausfälle."""
    heute = timezone.localdate()
    ich = plan.helfer_von(request.user)
    return render(request, "dienstplan/meine.html", {
        "ich": ich, "heute": heute,
        "dienste": plan.einsaetze(ich, heute, heute + dt.timedelta(days=27)) if ich else [],
        "ausfaelle": Ausfall.objects.filter(helfer=ich, bis__gte=heute) if ich else [],
        "darf_melden": plan.darf_selbst_melden(request.user),
        "planen": rollen.hat_recht(request.user, "dienstplan.planen"),
    })  # fmt: skip


@never_cache
@sehen
def ausfall(request):
    darf_planen = rollen.hat_recht(request.user, "dienstplan.planen")
    ich = plan.helfer_von(request.user)
    if not darf_planen and not plan.darf_selbst_melden(request.user):
        raise PermissionDenied
    heute = timezone.localdate()
    try:
        von = max(dt.date.fromisoformat(request.GET.get("von", "")), heute)
    except ValueError:
        von = heute
    form = AusfallForm(request.POST or None, planen=darf_planen,
                       initial={"von": von, "helfer": ich.pk if ich else None})  # fmt: skip
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        wer = d["helfer"] if darf_planen else ich
        a = plan.ausfall_melden(wer, d["von"], d["bis"], d["grund"], d["anmerkung"],
                                request.user.get_username(),
                                request.build_absolute_uri(reverse("dienstplan:plan")))  # fmt: skip
        anzahl = len(plan.einsaetze(wer, a.von, a.bis))
        messages.success(request, f"Ausfall eingetragen ({anzahl} Dienst(e) betroffen). Die "
                                  "Teamleitung wird benachrichtigt.")  # fmt: skip
        return redirect("dienstplan:plan" if darf_planen else "dienstplan:meine")
    return render(request, "dienstplan/ausfall.html", {
        "form": form,
        "zurueck": reverse("dienstplan:plan" if darf_planen else "dienstplan:meine"),
    })  # fmt: skip


@require_POST
@sehen
def ausfall_loeschen(request, pk):
    a = get_object_or_404(Ausfall, pk=pk)
    ich = plan.helfer_von(request.user)
    eigener = ich is not None and a.helfer_id == ich.pk and plan.darf_selbst_melden(request.user)
    if not (eigener or rollen.hat_recht(request.user, "dienstplan.planen")):
        raise PermissionDenied
    papierkorb.loeschen(request.user, "Ausfall im Dienstplan", str(a), a,
                        recht="dienstplan.planen")  # fmt: skip
    messages.success(request, "Ausfall zurückgenommen.")
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, {request.get_host()}):
        weiter = reverse("dienstplan:meine")
    return redirect(weiter)


# --- Einstellungen ----------------------------------------------------------------------------


@never_cache
@planen
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=DienstplanEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen des Dienstplans gespeichert.")
        return redirect("dienstplan:einstellungen")
    from apps.dienstplan import beispiel as muster

    dienststellen = {d.ausgabestelle_id: d for d in DienstStelle.objects.all()}
    return render(request, "dienstplan/einstellungen.html", {
        "form": form, "beispiel": muster.vorhanden(),
        "stellen": [(s, dienststellen.get(s.pk)) for s in Ausgabestelle.objects.filter(aktiv=True)
                    .order_by("name")],
        "helfer": helfer_aktiv(),
    })  # fmt: skip


@never_cache
@planen
def stelle(request, pk):
    """Eine Ausgabestelle: mitmachen ja/nein, Ausgabetage, je Tag Teamleitung, Aufgaben und
    feste Besetzung."""
    ausgabestelle = get_object_or_404(Ausgabestelle, pk=pk)
    ds, _ = DienstStelle.objects.get_or_create(ausgabestelle=ausgabestelle)
    tage = wochentage(ds.tage)
    tag = request.GET.get("tag") if request.GET.get("tag") in tage else (tage[0] if tage else "")
    hier = f"{reverse('dienstplan:stelle', args=[pk])}?tag={tag}"
    aktion = request.POST.get("aktion")
    form = StelleForm(request.POST if aktion == "stelle" else None, instance=ds)
    diensttag = Diensttag.objects.get_or_create(stelle=ds, wochentag=tag)[0] if tag else None
    tag_form = DiensttagForm(request.POST if aktion == "tag" else None, instance=diensttag)
    neu_form = AufgabeForm(request.POST if aktion == "aufgabe" else None)
    if request.method == "POST":
        if aktion == "stelle" and form.is_valid():
            form.save()
            messages.success(request, "Gespeichert.")
            return redirect(f"{reverse('dienstplan:stelle', args=[pk])}")
        if aktion == "tag" and diensttag and tag_form.is_valid():
            tag_form.save()
            messages.success(request, "Teamleitung gespeichert.")
            return redirect(hier)
        if aktion == "aufgabe" and tag and neu_form.is_valid():
            a = neu_form.save(commit=False)
            a.stelle, a.wochentag = ds, tag
            if not a.reihenfolge:
                a.reihenfolge = (
                    max(
                        ds.aufgaben.filter(wochentag=tag).values_list("reihenfolge", flat=True),
                        default=0,
                    )
                    + 1
                )
            a.save()
            messages.success(request, f"Aufgabe „{a}“ angelegt.")
            return redirect(hier)
        if aktion == "besetzung" and tag:
            _besetzung_speichern(request, ds, tag)
            messages.success(request, "Feste Besetzung gespeichert.")
            return redirect(hier)
        if aktion == "standard":
            ersetzen = request.POST.get("ersetzen")
            angelegt = plan.standard_anlegen(ds, ersetzen if ersetzen in tage else "")
            if angelegt:
                tage_text = ", ".join(TAGNAME[t] for t in angelegt)
                messages.success(request, f"Standard-Aufgaben angelegt für: {tage_text}.")
            else:
                messages.info(request, "An allen Ausgabetagen stehen schon Aufgaben; nichts "
                                       "angelegt.")  # fmt: skip
            return redirect(hier)
        if aktion == "kopieren" and tag and request.POST.get("von") in tage:
            anzahl = plan.tag_kopieren(ds, request.POST["von"], tag)
            messages.success(request, f"{anzahl} Aufgaben von {TAGNAME[request.POST['von']]} "
                                      "übernommen.")  # fmt: skip
            return redirect(hier)
    aufgaben = ds.aufgaben.filter(wochentag=tag).select_related("besetzung__helfer__konto")
    return render(request, "dienstplan/stelle.html", {
        "ausgabestelle": ausgabestelle, "ds": ds, "form": form, "tage": tage, "tag": tag,
        "tagname": TAGNAME.get(tag, ""), "tag_form": tag_form, "neu_form": neu_form,
        "aufgaben": aufgaben, "helfer": helfer_aktiv(),
        "andere_tage": [t for t in tage if t != tag],
    })  # fmt: skip


def _besetzung_speichern(request, ds, tag):
    gueltig = {str(h.pk): h for h in helfer_aktiv()}
    for a in ds.aufgaben.filter(wochentag=tag):
        wahl = request.POST.get(f"h_{a.pk}", "")
        if wahl in gueltig:
            Besetzung.objects.update_or_create(aufgabe=a, defaults={"helfer": gueltig[wahl]})
        elif not wahl:
            Besetzung.objects.filter(aufgabe=a).delete()


@never_cache
@planen
def aufgabe(request, pk):
    a = get_object_or_404(Aufgabe, pk=pk)
    zurueck = f"{reverse('dienstplan:stelle', args=[a.stelle.ausgabestelle_id])}?tag={a.wochentag}"
    form = AufgabeForm(request.POST or None, instance=a)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Aufgabe gespeichert.")
        return redirect(zurueck)
    return render(request, "dienstplan/aufgabe.html", {"form": form, "a": a, "zurueck": zurueck})


@require_POST
@planen
def aufgabe_loeschen(request, pk):
    a = get_object_or_404(Aufgabe, pk=pk)
    zurueck = f"{reverse('dienstplan:stelle', args=[a.stelle.ausgabestelle_id])}?tag={a.wochentag}"
    papierkorb.loeschen(request.user, "Aufgabe im Dienstplan", f"{a} ({a.stelle}, {a.wochentag})",
                        a, recht="dienstplan.planen")  # fmt: skip
    messages.success(request, "Aufgabe in den Papierkorb gelegt.")
    return redirect(zurueck)


@require_POST
@planen
@nicht_in_demo
def telegram_pruefen(request):
    from apps.core import telegram

    e = DienstplanEinstellungen.laden()
    if not telegram.schluessel(e):
        messages.error(request, "Bitte zuerst den Bot-Schlüssel speichern.")
        return redirect("dienstplan:einstellungen")
    try:
        if request.POST.get("aktion") == "test":
            if not telegram.chats(e):
                raise telegram.TelegramFehler("Bitte zuerst mindestens eine Chat-ID eintragen.")
            anzahl = telegram.senden(e, "✅ bintafeln: Testnachricht vom Dienstplan.")
            messages.success(request, f"Testnachricht an {anzahl} Chat(s) gesendet.")
        else:
            gefunden = telegram.gefundene_chats(e)
            if gefunden:
                messages.info(
                    request,
                    "Gefundene Chats (ID für „Telegram-Chats“): "
                    + "; ".join(f"{name}: {chat}" for chat, name in gefunden),
                )
            else:
                messages.info(request, "Noch keine Chats. Die Person schreibt dem Bot „/start“; "
                                       "dann noch einmal suchen.")  # fmt: skip
    except telegram.TelegramFehler as fehler:
        messages.error(request, str(fehler))
    return redirect("dienstplan:einstellungen")


@require_POST
@planen
def beispiel(request):
    from apps.dienstplan import beispiel as muster

    if request.POST.get("aktion") == "entfernen":
        anzahl = muster.entfernen()
        messages.success(request, f"Beispiel entfernt ({anzahl} erfundene Helfer gelöscht).")
    else:
        e = muster.anlegen()
        messages.success(
            request,
            f"Beispiel angelegt: Ausgabestelle „{e['stelle']}“, "
            f"{e['aufgaben']} Aufgaben, {e['helfer']} erfundene Helfer.",
        )
    return redirect("dienstplan:einstellungen")


@require_POST
@sehen
def ausfall_gesund(request, pk):
    """Wieder gesund ab heute (ADR 0085): kann einspringen, die eigenen Plätze bleiben frei."""
    a = get_object_or_404(Ausfall, pk=pk)
    ich = plan.helfer_von(request.user)
    eigener = ich is not None and a.helfer_id == ich.pk and plan.darf_selbst_melden(request.user)
    if not (eigener or rollen.hat_recht(request.user, "dienstplan.planen")):
        raise PermissionDenied
    if plan.gesund_melden(a, timezone.localdate(),
                          request.build_absolute_uri(reverse("dienstplan:plan"))):  # fmt: skip
        messages.success(request, "Wieder gesund gemeldet. Die eigenen Plätze bleiben frei "
                                  "bzw. beim Ersatz; bitte dort eintragen, wo noch jemand "
                                  "fehlt.")  # fmt: skip
    else:
        messages.info(request, "Dieser Ausfall ist schon vorbei oder bereits gesund gemeldet.")
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, {request.get_host()}):
        weiter = reverse("dienstplan:meine")
    return redirect(weiter)
