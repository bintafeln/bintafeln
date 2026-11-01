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

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import papierkorb
from apps.core.pdf import pdf_antwort
from apps.fahrdienst import plan
from apps.fahrdienst.forms import (
    AusfallForm,
    EinstellungenForm,
    SpringerForm,
    TourForm,
    fahrdienst_personen,
)
from apps.fahrdienst.models import (
    Ausfall,
    Besetzung,
    FahrdienstEinstellungen,
    Springer,
    Tour,
    platz_name,
)
from apps.konten import rollen
from apps.konten.views import nicht_in_demo

sehen = rollen.recht_erforderlich("fahrdienst.sehen")
planen = rollen.recht_erforderlich("fahrdienst.planen")
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
          "Oktober", "November", "Dezember"]  # fmt: skip


def _monat(text: str) -> dt.date:
    try:
        return dt.datetime.strptime(text, "%Y-%m").date()
    except (TypeError, ValueError):
        return timezone.localdate().replace(day=1)


def _gewaehlt(daten) -> dt.date:
    """Monat aus „?monat=JJJJ-MM“ oder aus der Auswahl Monat/Jahr auf der Planseite."""
    if daten.get("jahr") and daten.get("m"):
        return _monat(f"{daten['jahr']}-{daten['m']}")
    return _monat(daten.get("monat"))


def _verschieben(erster: dt.date, monate: int) -> dt.date:
    jahr, monat = divmod(erster.year * 12 + erster.month - 1 + monate, 12)
    return dt.date(jahr, monat + 1, 1)


@never_cache
@sehen
def uebersicht(request):
    """Der Fahrerplan eines Monats: Tage × Touren, Ausfälle gelb, offene Plätze rot. Jeder Monat
    lässt sich jederzeit wieder öffnen und ändern: Er ergibt sich aus der festen Besetzung, dazu
    Ausfälle und Ersatz je Tag."""
    erster = _gewaehlt(request.GET)
    jahr = timezone.localdate().year
    letzter = _verschieben(erster, 1) - dt.timedelta(days=1)
    tage = plan.tage(plan.fahrtage(erster, letzter))
    return render(request, "fahrdienst/plan.html", {
        "tage": tage, "touren": plan.touren(erster, letzter),
        "titel": f"{MONATE[erster.month - 1]} {erster.year}", "monat": f"{erster:%Y-%m}",
        "erster": erster, "monate": list(enumerate(MONATE, start=1)),
        "jahre": range(min(jahr - 2, erster.year), max(jahr + 1, erster.year) + 1),
        "vorher": f"{_verschieben(erster, -1):%Y-%m}",
        "nachher": f"{_verschieben(erster, 1):%Y-%m}",
        "heute": timezone.localdate(),
        "planen": rollen.hat_recht(request.user, "fahrdienst.planen"),
        "offen": sum(p.fehlt for _, z in tage for _, ps in z for p in ps),
        "darf_melden": plan.darf_selbst_melden(request.user),
        **_karten(tage),
    })  # fmt: skip


def _karten(tage) -> dict:
    """Derselbe Plan für schmale Bildschirme: eine Karte je Fahrtag mit den Touren, die an dem
    Tag fahren. Aufgeklappt ist der nächste Fahrtag; vergangene Tage stehen eingeklappt unter
    „Frühere Tage“."""
    heute = timezone.localdate()
    naechster = next((d for d, _ in tage if d >= heute), None)
    karten = [{"datum": datum, "touren": [(t, ps) for t, ps in zeile if ps],
               "offen": datum == naechster, "fehlen": sum(p.fehlt for _, ps in zeile for p in ps)}
              for datum, zeile in tage]  # fmt: skip
    return {"karten_frueher": [k for k in karten if k["datum"] < heute],
            "karten": [k for k in karten if k["datum"] >= heute]}  # fmt: skip


@never_cache
@sehen
def plan_pdf(request):
    """Der Monat als PDF zum Aushängen (A3 quer)."""
    from apps.fahrdienst import pdf

    erster = _monat(request.GET.get("monat"))
    letzter = _verschieben(erster, 1) - dt.timedelta(days=1)
    titel = f"{MONATE[erster.month - 1]} {erster.year}"
    inhalt = pdf.monat(titel, plan.tage(plan.fahrtage(erster, letzter)),
                       plan.touren(erster, letzter))  # fmt: skip
    return pdf_antwort(inhalt, f"fahrerplan-{erster:%Y-%m}.pdf")


@never_cache
@planen
def platz(request, datum, tour, nr):
    """Ersatz für einen Platz an einem Tag eintragen oder zurücknehmen."""
    try:
        tag = dt.date.fromisoformat(datum)
    except ValueError as fehler:
        raise Http404 from fehler
    t = get_object_or_404(Tour, pk=tour)
    if not 1 <= nr <= t.plaetze or not t.faehrt_am(tag):
        raise Http404
    zurueck = f"{reverse('fahrdienst:plan')}?monat={tag:%Y-%m}"
    nur_fahrer = nr == 1
    if request.method == "POST":
        wahl, gast = request.POST.get("benutzer", ""), request.POST.get("gast", "").strip()
        neu = (get_object_or_404(fahrdienst_personen(nur_fahrer=nur_fahrer), pk=wahl)
               if wahl else None)  # fmt: skip
        springer, weitere = plan.verfuegbar(tag, nur_fahrer=nur_fahrer)
        if neu is not None and neu not in springer + weitere:
            # z. B. selbst als ausgefallen gemeldet oder an dem Tag schon eingeteilt
            messages.error(request, f"{neu.name} kann am {tag:%d.%m.%Y} nicht einspringen "
                                    "(Ausfall gemeldet oder schon eingeteilt).")  # fmt: skip
            return redirect(request.path)
        plan.ersatz_eintragen(tag, t, nr, neu, request.user.get_username(), gast=gast)
        if neu:
            text = f"{neu.name} springt ein."
        else:
            text = f"Gast „{gast}“ fährt mit." if gast else "Eintrag zurückgenommen."
        messages.success(request, f"{tag:%d.%m.%Y}, {t}, {platz_name(nr)}: {text}")
        return redirect(zurueck)
    springer, weitere = plan.verfuegbar(tag, nur_fahrer=nur_fahrer)
    return render(request, "fahrdienst/platz.html", {
        "p": plan.platz(tag, t, nr), "springer": springer, "weitere": weitere,
        "zurueck": zurueck, "wochentag": WOCHENTAGE[tag.weekday()], "monat": f"{tag:%Y-%m}",
        "ausfall_form": AusfallForm(planen=True),
    })  # fmt: skip


@never_cache
@sehen
def meine(request):
    """Eigene Einsätze der nächsten vier Wochen und eigene Ausfälle."""
    heute = timezone.localdate()
    ich = plan.person_von(request.user)
    return render(request, "fahrdienst/meine.html", {
        "ich": ich,
        "einsaetze": plan.einsaetze(ich, heute, heute + dt.timedelta(days=27)),
        "heute": heute,
        "ausfaelle": Ausfall.objects.filter(person=ich, bis__gte=heute) if ich else [],
        "darf_melden": plan.darf_selbst_melden(request.user),
        "planen": rollen.hat_recht(request.user, "fahrdienst.planen"),
    })  # fmt: skip


@never_cache
@sehen
def ausfall(request):
    darf_planen = rollen.hat_recht(request.user, "fahrdienst.planen")
    if not darf_planen and not plan.darf_selbst_melden(request.user):
        raise PermissionDenied
    ich = plan.person_von(request.user)
    heute = timezone.localdate()
    try:  # aus dem Plan oder „Meine Einsätze“: der angetippte Tag
        von = max(dt.date.fromisoformat(request.GET.get("von", "")), heute)
    except ValueError:
        von = heute
    vorbelegt = {"von": von, "person": ich.pk if ich else None}
    form = AusfallForm(request.POST or None, planen=darf_planen, initial=vorbelegt)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        wer = d["person"] if darf_planen else ich
        a = plan.ausfall_melden(wer, d["von"], d["bis"], d["grund"], d["anmerkung"],
                                request.user.get_username(),
                                request.build_absolute_uri(reverse("fahrdienst:plan"))
                                + f"?monat={d['von']:%Y-%m}")  # fmt: skip
        betroffen = len(plan.einsaetze(wer, a.von, a.bis))
        messages.success(request, f"Ausfall eingetragen ({betroffen} Einsatz/Einsätze betroffen). "
                                  "Die Fahrdienstleitung wird benachrichtigt.")  # fmt: skip
        if darf_planen:
            return redirect(f"{reverse('fahrdienst:plan')}?monat={a.von:%Y-%m}")
        return redirect("fahrdienst:meine")
    return render(request, "fahrdienst/ausfall.html", {
        "form": form, "zurueck": reverse("fahrdienst:plan" if darf_planen else "fahrdienst:meine"),
    })  # fmt: skip


@require_POST
@sehen
def ausfall_loeschen(request, pk):
    a = get_object_or_404(Ausfall, pk=pk)
    eigener = (
        a.person and a.person.konto_id == request.user.pk and plan.darf_selbst_melden(request.user)
    )
    if not (eigener or rollen.hat_recht(request.user, "fahrdienst.planen")):
        raise PermissionDenied
    papierkorb.loeschen(request.user, "Ausfall im Fahrdienst", str(a), a,
                        recht="fahrdienst.planen")  # fmt: skip
    messages.success(request, "Ausfall zurückgenommen.")
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, {request.get_host()}):
        weiter = reverse("fahrdienst:meine")  # nur Adressen dieser Installation
    return redirect(weiter)


@never_cache
@planen
def einstellungen(request):
    e = FahrdienstEinstellungen.laden()
    form = EinstellungenForm(request.POST or None, instance=e)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("fahrdienst:einstellungen")
    heute = timezone.localdate()
    from apps.fahrdienst import beispiel as muster

    return render(request, "fahrdienst/einstellungen.html", {
        "form": form, "touren": Tour.objects.all(), "beispiel": muster.vorhanden(),
        "springer": Springer.objects.select_related("person"),
        "ausfaelle": Ausfall.objects.filter(bis__gte=heute).select_related("person"),
    })  # fmt: skip


@require_POST
@planen
@nicht_in_demo
def telegram_pruefen(request):
    """„Chats suchen“ (wer dem Bot geschrieben hat) oder „Testnachricht senden“."""
    from apps.core import telegram

    e = FahrdienstEinstellungen.laden()
    if not telegram.schluessel(e):
        messages.error(request, "Bitte zuerst den Bot-Schlüssel speichern.")
        return redirect("fahrdienst:einstellungen")
    try:
        if request.POST.get("aktion") == "test":
            if not telegram.chats(e):
                raise telegram.TelegramFehler("Bitte zuerst mindestens eine Chat-ID eintragen.")
            anzahl = telegram.senden(e, "✅ bintafeln: Testnachricht vom Fahrdienst.")
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
                messages.info(request, "Noch keine Chats. Die Person schreibt dem Bot in Telegram "
                                       "„/start“; dann noch einmal suchen.")  # fmt: skip
    except telegram.TelegramFehler as fehler:
        messages.error(request, str(fehler))
    return redirect("fahrdienst:einstellungen")


@require_POST
@planen
def beispiel(request):
    """Beispiel-Fahrerplan zum Ausprobieren anlegen oder wieder entfernen."""
    from apps.fahrdienst import beispiel as muster

    if request.POST.get("aktion") == "entfernen":
        anzahl = muster.entfernen()
        messages.success(request, f"Beispiel entfernt ({anzahl} erfundene Personen gelöscht).")
    else:
        z = muster.anlegen()
        messages.success(request, f"Beispiel angelegt: {z['Touren']} Touren, {z['Personen']} "
                                  "erfundene Fahrer und Beifahrer, zufällig verteilt.")  # fmt: skip
    return redirect("fahrdienst:plan")


@never_cache
@planen
def tour(request, pk=None):
    t = get_object_or_404(Tour, pk=pk) if pk else None
    form = TourForm(request.POST or None, instance=t)
    if request.method == "POST" and form.is_valid():
        t = form.save()
        messages.success(request, f"Tour „{t}“ gespeichert.")
        return redirect("fahrdienst:besetzung", pk=t.pk)
    return render(request, "fahrdienst/tour.html", {"form": form, "tour": t})


@require_POST
@planen
def tour_loeschen(request, pk):
    t = get_object_or_404(Tour, pk=pk)
    papierkorb.loeschen(request.user, "Tour", t.name, t, recht="fahrdienst.planen")
    messages.success(request, f"Tour „{t.name}“ mit fester Besetzung in den Papierkorb gelegt.")
    return redirect("fahrdienst:einstellungen")


@never_cache
@planen
def besetzung(request, pk):
    """Feste Besetzung einer Tour: je Fahrtag und Platz eine Person (Auswahl)."""
    t = get_object_or_404(Tour, pk=pk)
    tage = wochentage(FahrdienstEinstellungen.laden().fahrtage)
    personen = list(fahrdienst_personen())
    fahrer_pks = set(fahrdienst_personen(nur_fahrer=True).values_list("pk", flat=True))
    fahrer = [p for p in personen if p.pk in fahrer_pks]
    jetzt = {(b.wochentag, b.platz): b for b in t.besetzungen.all()}
    # Vom Fahrerplan aus geöffnet: danach zurück zu diesem Monat
    monat = request.GET.get("monat", "")
    zurueck = (f"{reverse('fahrdienst:plan')}?monat={_monat(monat):%Y-%m}" if monat
               else reverse("fahrdienst:einstellungen"))  # fmt: skip
    if request.method == "POST":
        gueltig = {str(p.pk): p for p in personen}
        nicht_fahrer = False
        for tag in tage:
            for nr in range(1, t.plaetze + 1):
                wahl = request.POST.get(f"b_{tag}_{nr}", "")
                alt = jetzt.get((tag, nr))
                if wahl in gueltig and nr == 1 and gueltig[wahl].pk not in fahrer_pks:
                    nicht_fahrer = True  # Fahrerplatz braucht einen Fahrer
                    continue
                if wahl in gueltig and (alt is None or str(alt.person_id) != wahl):
                    Besetzung.objects.update_or_create(
                        tour=t, wochentag=tag, platz=nr, defaults={"person": gueltig[wahl]}
                    )
                elif not wahl and alt is not None:
                    alt.delete()
        if nicht_fahrer:
            messages.warning(request, "Auf dem Fahrerplatz (Platz 1) kann nur ein Fahrer stehen; "
                                      "diese Auswahl wurde übergangen.")  # fmt: skip
        messages.success(request, f"Feste Besetzung der Tour „{t}“ gespeichert.")
        return redirect(zurueck)
    zeilen = [(tag, [(nr, platz_name(nr), jetzt.get((tag, nr)), nr == 1)
                     for nr in range(1, t.plaetze + 1)])
              for tag in tage]  # fmt: skip
    return render(request, "fahrdienst/besetzung.html",
                  {"tour": t, "zeilen": zeilen, "personen": personen, "fahrer": fahrer,
                   "zurueck": zurueck, "vom_plan": bool(monat)})  # fmt: skip


@never_cache
@planen
def springer(request, pk=None):
    s = get_object_or_404(Springer, pk=pk) if pk else None
    form = SpringerForm(request.POST or None, instance=s)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Springer gespeichert.")
        return redirect("fahrdienst:einstellungen")
    return render(request, "fahrdienst/springer.html", {"form": form, "springer": s})


@require_POST
@planen
def springer_loeschen(request, pk):
    s = get_object_or_404(Springer, pk=pk)
    papierkorb.loeschen(request.user, "Springer", str(s), s, recht="fahrdienst.planen")
    messages.success(request, f"„{s}“ ist kein Springer mehr.")
    return redirect("fahrdienst:einstellungen")


@require_POST
@sehen
def ausfall_gesund(request, pk):
    """Wieder gesund ab heute (ADR 0085): kann einspringen, die eigenen Plätze bleiben frei."""
    a = get_object_or_404(Ausfall, pk=pk)
    eigener = (
        a.person and a.person.konto_id == request.user.pk and plan.darf_selbst_melden(request.user)
    )
    if not (eigener or rollen.hat_recht(request.user, "fahrdienst.planen")):
        raise PermissionDenied
    if plan.gesund_melden(a, timezone.localdate(),
                          request.build_absolute_uri(reverse("fahrdienst:plan"))):  # fmt: skip
        messages.success(request, "Wieder gesund gemeldet. Die eigenen Plätze bleiben frei "
                                  "bzw. beim Ersatz; bitte dort eintragen, wo noch jemand "
                                  "fehlt.")  # fmt: skip
    else:
        messages.info(request, "Dieser Ausfall ist schon vorbei oder bereits gesund gemeldet.")
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, {request.get_host()}):
        weiter = reverse("fahrdienst:meine")
    return redirect(weiter)
