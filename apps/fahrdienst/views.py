import datetime as dt

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import papierkorb
from apps.core.pdf import pdf_antwort
from apps.fahrdienst import plan
from apps.fahrdienst.forms import AusfallForm, EinstellungenForm, SpringerForm, TourForm, aktive
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


def _verschieben(erster: dt.date, monate: int) -> dt.date:
    jahr, monat = divmod(erster.year * 12 + erster.month - 1 + monate, 12)
    return dt.date(jahr, monat + 1, 1)


@never_cache
@sehen
def uebersicht(request):
    """Der Fahrerplan eines Monats: Tage × Touren, Ausfälle gelb, offene Plätze rot."""
    erster = _monat(request.GET.get("monat"))
    letzter = _verschieben(erster, 1) - dt.timedelta(days=1)
    tage = plan.tage(plan.fahrtage(erster, letzter))
    return render(request, "fahrdienst/plan.html", {
        "tage": tage, "touren": list(Tour.objects.filter(aktiv=True)),
        "titel": f"{MONATE[erster.month - 1]} {erster.year}", "monat": f"{erster:%Y-%m}",
        "vorher": f"{_verschieben(erster, -1):%Y-%m}",
        "nachher": f"{_verschieben(erster, 1):%Y-%m}",
        "heute": timezone.localdate(),
        "planen": rollen.hat_recht(request.user, "fahrdienst.planen"),
        "offen": sum(p.status == plan.OFFEN for _, z in tage for _, ps in z for p in ps),
        "darf_melden": plan.darf_selbst_melden(request.user),
    })  # fmt: skip


@never_cache
@sehen
def plan_pdf(request):
    """Der Monat als PDF zum Aushängen (A3 quer)."""
    from apps.fahrdienst import pdf

    erster = _monat(request.GET.get("monat"))
    letzter = _verschieben(erster, 1) - dt.timedelta(days=1)
    titel = f"{MONATE[erster.month - 1]} {erster.year}"
    inhalt = pdf.monat(titel, plan.tage(plan.fahrtage(erster, letzter)),
                       list(Tour.objects.filter(aktiv=True)))  # fmt: skip
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
    if not 1 <= nr <= t.plaetze:
        raise Http404
    zurueck = f"{reverse('fahrdienst:plan')}?monat={tag:%Y-%m}"
    if request.method == "POST":
        wahl = request.POST.get("benutzer", "")
        neu = get_object_or_404(aktive(), pk=wahl) if wahl else None
        plan.ersatz_eintragen(tag, t, nr, neu, request.user.get_username())
        messages.success(request, f"{tag:%d.%m.%Y}, {t}, {platz_name(nr)}: "
                                  + (f"{neu.get_full_name() or neu} springt ein."
                                     if neu else "Ersatz zurückgenommen."))  # fmt: skip
        return redirect(zurueck)
    springer, weitere = plan.verfuegbar(tag)
    return render(request, "fahrdienst/platz.html", {
        "p": plan.platz(tag, t, nr), "springer": springer, "weitere": weitere,
        "zurueck": zurueck, "wochentag": WOCHENTAGE[tag.weekday()],
    })  # fmt: skip


@never_cache
@sehen
def meine(request):
    """Eigene Einsätze der nächsten vier Wochen und eigene Ausfälle."""
    heute = timezone.localdate()
    return render(request, "fahrdienst/meine.html", {
        "einsaetze": plan.einsaetze(request.user, heute, heute + dt.timedelta(days=27)),
        "ausfaelle": Ausfall.objects.filter(benutzer=request.user, bis__gte=heute),
        "darf_melden": plan.darf_selbst_melden(request.user),
        "planen": rollen.hat_recht(request.user, "fahrdienst.planen"),
    })  # fmt: skip


@never_cache
@sehen
def ausfall(request):
    darf_planen = rollen.hat_recht(request.user, "fahrdienst.planen")
    if not darf_planen and not plan.darf_selbst_melden(request.user):
        raise PermissionDenied
    vorbelegt = {"von": timezone.localdate(), "benutzer": request.user.pk}
    form = AusfallForm(request.POST or None, planen=darf_planen, initial=vorbelegt)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        wer = d["benutzer"] if darf_planen else request.user
        a = plan.ausfall_melden(wer, d["von"], d["bis"], d["grund"], d["anmerkung"],
                                request.user.get_username(),
                                request.build_absolute_uri(reverse("fahrdienst:plan"))
                                + f"?monat={d['von']:%Y-%m}")  # fmt: skip
        betroffen = len(plan.einsaetze(wer, a.von, a.bis))
        messages.success(request, f"Ausfall eingetragen ({betroffen} Einsatz/Einsätze betroffen). "
                                  "Die Fahrdienstleitung wird benachrichtigt.")  # fmt: skip
        return redirect("fahrdienst:plan" if darf_planen else "fahrdienst:meine")
    return render(request, "fahrdienst/ausfall.html", {"form": form})


@require_POST
@sehen
def ausfall_loeschen(request, pk):
    a = get_object_or_404(Ausfall, pk=pk)
    eigener = a.benutzer_id == request.user.pk and plan.darf_selbst_melden(request.user)
    if not (eigener or rollen.hat_recht(request.user, "fahrdienst.planen")):
        raise PermissionDenied
    papierkorb.loeschen(request.user, "Ausfall im Fahrdienst", str(a), a,
                        recht="fahrdienst.planen")  # fmt: skip
    messages.success(request, "Ausfall zurückgenommen.")
    return redirect(request.POST.get("weiter") or "fahrdienst:meine")


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
    return render(request, "fahrdienst/einstellungen.html", {
        "form": form, "touren": Tour.objects.all(),
        "springer": Springer.objects.select_related("benutzer"),
        "ausfaelle": Ausfall.objects.filter(bis__gte=heute).select_related("benutzer"),
    })  # fmt: skip


@require_POST
@planen
@nicht_in_demo
def telegram_pruefen(request):
    """„Chats suchen“ (wer dem Bot geschrieben hat) oder „Testnachricht senden“."""
    from apps.fahrdienst import telegram

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
    personen = list(aktive())
    jetzt = {(b.wochentag, b.platz): b for b in t.besetzungen.all()}
    if request.method == "POST":
        gueltig = {str(p.pk): p for p in personen}
        for tag in tage:
            for nr in range(1, t.plaetze + 1):
                wahl = request.POST.get(f"b_{tag}_{nr}", "")
                alt = jetzt.get((tag, nr))
                if wahl in gueltig and (alt is None or str(alt.benutzer_id) != wahl):
                    Besetzung.objects.update_or_create(
                        tour=t, wochentag=tag, platz=nr, defaults={"benutzer": gueltig[wahl]}
                    )
                elif not wahl and alt is not None:
                    alt.delete()
        messages.success(request, f"Feste Besetzung der Tour „{t}“ gespeichert.")
        return redirect("fahrdienst:einstellungen")
    zeilen = [(tag, [(nr, platz_name(nr), jetzt.get((tag, nr))) for nr in range(1, t.plaetze + 1)])
              for tag in tage]  # fmt: skip
    return render(request, "fahrdienst/besetzung.html",
                  {"tour": t, "zeilen": zeilen, "personen": personen})  # fmt: skip


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
