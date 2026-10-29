"""Warteliste (Modul, ADR 0051): Liste, Einladen, Termine, Abgleich, Dubletten, Streichungen."""

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.antraege.models import Antrag
from apps.core import papierkorb
from apps.core.pdf import Pdf, pdf_antwort
from apps.konten import rollen
from apps.warteliste import ablauf
from apps.warteliste.forms import EinladenForm, EinstellungenForm, StatusForm, TerminForm
from apps.warteliste.models import (
    AbgleichEntscheidung,
    Streichung,
    Termin,
    WartelisteEinstellungen,
    Wartestand,
)

# Spalten der Warteliste, die man ausblenden kann (static/js/spalten.js); Name bleibt immer
SPALTEN = [("eingang", "Eingang"), ("nummer", "#"), ("geburtsdatum", "Geburtsdatum"),
           ("kontakt", "Kontakt"), ("wohnort", "Wohnort"), ("personen", "Personen"),
           ("art", "Art"), ("staat", "Staatsangehörigkeit"), ("status", "Status"),
           ("termin", "Termin"), ("anmerkung", "Anmerkung")]  # fmt: skip

sehen = rollen.recht_erforderlich("warteliste.sehen")
bearbeiten = rollen.recht_erforderlich("warteliste.bearbeiten")
S = Wartestand.Status
SORTIERUNG = {"eingang": "antrag__eingegangen_am", "name": "antrag__nachname",
              "status": "status", "termin": "termin__datum", "staat":
              "antrag__staatsangehoerigkeit", "art": "antrag__art"}  # fmt: skip


def _von(request) -> str:
    return (request.user.get_full_name() or request.user.get_username())[:150]


def _gefiltert(request):
    f = {
        "status": request.GET.get("status", ""),
        "art": request.GET.get("art", ""),
        "staat_modus": request.GET.get("staat_modus", "alle"),
        "staaten": request.GET.getlist("staat"),
        "termin": request.GET.get("termin", ""),
        "suche": request.GET.get("suche", "").strip(),
        "sort": request.GET.get("sort", "eingang"),
    }
    ws = Wartestand.objects.filter(antrag__papierkorb_am__isnull=True).select_related(
        "antrag", "termin"
    )
    if f["status"] in S.values:
        ws = ws.filter(status=f["status"])
    else:
        f["status"] = ""
        ws = ws.exclude(status__in=Wartestand.ABGESCHLOSSEN)
    if f["art"] in Antrag.Art.values:
        ws = ws.filter(antrag__art=f["art"])
    if f["staaten"] and f["staat_modus"] == "nur":
        ws = ws.filter(antrag__staatsangehoerigkeit__in=f["staaten"])
    elif f["staaten"] and f["staat_modus"] == "nicht":
        ws = ws.exclude(antrag__staatsangehoerigkeit__in=f["staaten"])
    if f["termin"] == "mit":
        ws = ws.filter(termin__isnull=False)
    elif f["termin"] == "ohne":
        ws = ws.filter(termin__isnull=True)
    elif f["termin"].isdigit():
        ws = ws.filter(termin_id=int(f["termin"]))
    for wort in f["suche"].split():
        teile = Q(antrag__vorname__icontains=wort) | Q(antrag__nachname__icontains=wort)
        teile |= Q(antrag__email__icontains=wort) | Q(antrag__telefon__icontains=wort)
        teile |= Q(antrag__staatsangehoerigkeit__icontains=wort)
        if wort.isdigit():
            teile |= Q(antrag__laufnummer=int(wort))
        ws = ws.filter(teile)
    feld = SORTIERUNG.get(f["sort"].lstrip("-"))
    if not feld:
        f["sort"], feld = "eingang", SORTIERUNG["eingang"]
    ws = ws.order_by(("-" if f["sort"].startswith("-") else "") + feld, "antrag__pk")
    return f, ws


@never_cache
@sehen
def liste(request):
    ablauf.automatik()
    f, ws = _gefiltert(request)
    zahlen = dict(Wartestand.objects.filter(antrag__papierkorb_am__isnull=True)
                  .values_list("status").annotate(n=Count("pk")))  # fmt: skip
    staaten = sorted(set(Antrag.objects.filter(papierkorb_am__isnull=True)
                         .exclude(staatsangehoerigkeit="")
                         .values_list("staatsangehoerigkeit", flat=True)))  # fmt: skip
    termine = Termin.objects.annotate(n=Count("wartende")).filter(n__gt=0)
    pruefen = [w.antrag for w in ws if w.status in (S.NEU, S.WARTEND, S.WARTEZEIT_UM)]
    sperren = ablauf.offene_sperren(pruefen)
    return render(request, "warteliste/liste.html", {
        "eintraege": ws.prefetch_related("antrag__personen", "antrag__anmerkungen"), "f": f,
        "staaten": staaten, "termine": termine, "sperren": sperren, "spalten_wahl": SPALTEN,
        "status_zahlen": [(s, name, zahlen.get(s, 0)) for s, name in S.choices],
        "arten": Antrag.Art.choices,
        "einladen": EinladenForm(termine=ablauf.kommende_termine()),
        "status_form": StatusForm(),
    })  # fmt: skip


def _ausgewaehlt(request):
    ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    return list(Antrag.objects.filter(pk__in=ids, papierkorb_am__isnull=True)
                .order_by("eingegangen_am"))  # fmt: skip


@require_POST
@bearbeiten
def einladen(request):
    antraege = _ausgewaehlt(request)
    form = EinladenForm(request.POST, termine=ablauf.kommende_termine())
    if not antraege:
        messages.error(request, "Bitte mindestens einen Antrag auswählen.")
        return redirect("warteliste:liste")
    if not form.is_valid():
        for fehler in form.errors.values():
            messages.error(request, " ".join(fehler))
        return redirect("warteliste:liste")
    termin = form.termin_holen()
    ergebnisse = ablauf.einladen(antraege, termin, _von(request),
                                 mail_senden=form.cleaned_data["mail"])  # fmt: skip
    return render(request, "warteliste/ergebnis.html", {
        "titel": f"Einladungen zum Termin {termin}", "ergebnisse": ergebnisse, "termin": termin,
    })  # fmt: skip


@require_POST
@bearbeiten
def status_mehrere(request):
    antraege = _ausgewaehlt(request)
    form = StatusForm(request.POST)
    if not antraege or not form.is_valid():
        messages.error(request, "Bitte Anträge und einen Status wählen (bei Wartezeit mit Datum).")
        return redirect("warteliste:liste")
    for a in antraege:
        ws, _ = Wartestand.objects.get_or_create(antrag=a)
        ablauf.status_setzen(ws, form.cleaned_data["status"], _von(request),
                             form.cleaned_data.get("wartezeit_bis"))  # fmt: skip
    messages.success(request, f"Status bei {len(antraege)} Antr"
                     f"{'ag' if len(antraege) == 1 else 'ägen'} gesetzt.")  # fmt: skip
    zurueck = request.POST.get("zurueck", "")
    if url_has_allowed_host_and_scheme(zurueck, allowed_hosts={request.get_host()}):
        return redirect(zurueck)
    return redirect("warteliste:liste")


@never_cache
@sehen
def eintrag(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    ws, _ = Wartestand.objects.get_or_create(antrag=a)
    form = StatusForm(
        request.POST or None, initial={"status": ws.status, "wartezeit_bis": ws.wartezeit_bis}
    )
    if request.method == "POST":
        if not rollen.hat_recht(request.user, "warteliste.bearbeiten"):
            messages.error(request, "Dafür fehlt Ihnen das Recht.")
        elif "anmerkung" in request.POST:
            if text := request.POST["anmerkung"].strip()[:2000]:
                ablauf.anmerken(a, text, _von(request))
                messages.success(request, "Anmerkung gespeichert.")
            return redirect("warteliste:eintrag", a.pk)
        elif form.is_valid():
            ablauf.status_setzen(ws, form.cleaned_data["status"], _von(request),
                                 form.cleaned_data.get("wartezeit_bis"))  # fmt: skip
            messages.success(request, f"Status von Antrag {a.nummer} gesetzt.")
            return redirect("warteliste:eintrag", a.pk)
    return render(request, "warteliste/eintrag.html", {
        "a": a, "ws": ws, "form": form, "einladungen": a.einladungen.all(),
        "anmerkungen": a.anmerkungen.all(),
        "treffer": next(iter(ablauf.kundenabgleich(Antrag.objects.filter(pk=a.pk))),
                        {}).get("treffer", []),  # fmt: skip
        "einladen": EinladenForm(termine=ablauf.kommende_termine()),
    })  # fmt: skip


# ── Termine ──────────────────────────────────────────────────────────────────


@never_cache
@sehen
def termine(request):
    heute = timezone.localdate()
    alle = Termin.objects.annotate(
        eingeladen=Count("wartende", filter=Q(wartende__status=S.EINGELADEN)),
        erschienen=Count("wartende", filter=Q(wartende__status=S.ERSCHIENEN)),
        gesamt=Count("wartende"),
    )  # fmt: skip
    return render(request, "warteliste/termine.html", {
        "kommend": alle.filter(datum__gte=heute),
        "vergangen": alle.filter(datum__lt=heute).order_by("-datum", "-von")[:30],
    })  # fmt: skip


@never_cache
@bearbeiten
def termin_bearbeiten(request, pk=None):
    t = get_object_or_404(Termin, pk=pk) if pk else Termin()
    form = TerminForm(request.POST or None, instance=t)
    if request.method == "POST" and form.is_valid():
        t = form.save()
        messages.success(request, f"Termin {t} gespeichert.")
        return redirect("warteliste:termin", t.pk)
    return render(
        request, "warteliste/termin_bearbeiten.html", {"form": form, "t": t if pk else None}
    )


@never_cache
@sehen
def termin(request, pk):
    t = get_object_or_404(Termin, pk=pk)
    wartende = t.wartende.select_related("antrag").order_by("antrag__nachname", "antrag__vorname")
    return render(request, "warteliste/termin.html", {
        "t": t, "wartende": wartende, "status_form": StatusForm(),
        "ort": ablauf.ort(t),
    })  # fmt: skip


@require_POST
@bearbeiten
def termin_absagen(request, pk):
    t = get_object_or_404(Termin, pk=pk)
    antraege = _ausgewaehlt(request)
    if not antraege:
        messages.error(request, "Bitte mindestens eine Person auswählen.")
        return redirect("warteliste:termin", t.pk)
    ergebnisse = ablauf.absagen(t, antraege, _von(request))
    return render(request, "warteliste/ergebnis.html", {
        "titel": f"Absagen zum Termin {t}", "ergebnisse": ergebnisse, "termin": t,
    })  # fmt: skip


@require_POST
@bearbeiten
def termin_loeschen(request, pk):
    t = get_object_or_404(Termin, pk=pk)
    if t.wartende.filter(status=S.EINGELADEN).exists():
        messages.error(request, "Zu diesem Termin sind noch Personen eingeladen. Bitte erst "
                       "absagen.")  # fmt: skip
        return redirect("warteliste:termin", t.pk)
    papierkorb.loeschen(request.user, "Termin der Warteliste", str(t), t,
                        recht="warteliste.bearbeiten")  # fmt: skip
    messages.success(request, "Termin in den Papierkorb gelegt.")
    return redirect("warteliste:termine")


@sehen
def druckliste(request, pk):
    t = get_object_or_404(Termin, pk=pk)
    wartende = (
        t.wartende.select_related("antrag")
        .exclude(status=S.GESTRICHEN)
        .order_by("antrag__nachname", "antrag__vorname")
    )
    doc = Pdf(f"Termin {t}", "Liste der Eingeladenen")
    doc.absatz(ablauf.ort(t).replace("\n", ", "), klein=True)
    doc.tabelle(
        ["", "Antrag", "Name", "Telefon", "Staatsangehörigkeit", "Status"],
        [["", ws.antrag.nummer, f"{ws.antrag.nachname}, {ws.antrag.vorname}",
          ws.antrag.telefon, ws.antrag.staatsangehoerigkeit, ws.get_status_display()]
         for ws in wartende],
        breiten=[0.05, 0.1, 0.3, 0.2, 0.2, 0.15],
    )  # fmt: skip
    return pdf_antwort(doc.erzeugen(), f"druckliste_{t.datum:%Y-%m-%d}.pdf")


# ── Abgleich, Dubletten, Streichungen ────────────────────────────────────────


@never_cache
@bearbeiten
def abgleich(request):
    alle = request.GET.get("alle") == "1"
    antraege = ablauf.offene_antraege()
    if not alle:
        antraege = antraege.filter(wartestand__status__in=[S.NEU, S.WARTEND])
    return render(request, "warteliste/abgleich.html", {
        "ergebnis": ablauf.kundenabgleich(antraege.order_by("eingegangen_am")), "alle": alle,
        "geprueft": antraege.count(),
        "entschieden": AbgleichEntscheidung.objects.select_related("antrag")[:30],
    })  # fmt: skip


@require_POST
@bearbeiten
def abgleich_entscheiden(request):
    """Treffer des Abgleichs bestätigen („derselbe Haushalt“) oder verwerfen; oder zurücknehmen."""
    if pk := request.POST.get("zuruecknehmen"):
        AbgleichEntscheidung.objects.filter(pk=pk).delete()
        messages.success(
            request,
            "Prüfung zurückgenommen; der Treffer steht wieder in der Liste. "
            "Eine schon gesetzte Wartezeit bleibt (Status von Hand ändern).",
        )
        return redirect("warteliste:abgleich")
    a = get_object_or_404(Antrag, pk=request.POST.get("antrag"))
    kundennummer = request.POST.get("kundennummer", "").strip()
    try:
        meldung = ablauf.entscheiden(a, kundennummer, request.POST.get("gleich") == "1",
                                     _von(request))  # fmt: skip
    except ValueError as fehler:
        messages.error(request, str(fehler))
    else:
        messages.success(request, meldung)
    weiter = request.POST.get("weiter", "")
    return redirect(weiter if weiter.startswith("/warteliste/") else "warteliste:abgleich")


@never_cache
@bearbeiten
def dubletten(request):
    return render(request, "warteliste/dubletten.html", {"paare": ablauf.dubletten()})


@require_POST
@bearbeiten
def dublette(request):
    a = get_object_or_404(Antrag, pk=request.POST.get("a"))
    b = get_object_or_404(Antrag, pk=request.POST.get("b"))
    aktion = request.POST.get("aktion")
    if aktion == "ignorieren":
        ablauf.ignorieren(a, b, request.user)
        messages.success(request, f"Anträge {a.nummer} und {b.nummer}: keine Dublette.")
    elif aktion == "a_streichen":
        ablauf.zusammenfuehren(b, a, _von(request))
        messages.success(request, f"Antrag {a.nummer} gestrichen, bei {b.nummer} vermerkt.")
    elif aktion == "b_streichen":
        ablauf.zusammenfuehren(a, b, _von(request))
        messages.success(request, f"Antrag {b.nummer} gestrichen, bei {a.nummer} vermerkt.")
    return redirect("warteliste:dubletten")


@never_cache
@sehen
def streichungsliste(request):
    eintraege = Streichung.objects.all()
    q = request.GET.get("q", "").strip()
    for wort in q.split():
        eintraege = eintraege.filter(
            Q(name__icontains=wort)
            | Q(antragsnummer__icontains=wort)
            | Q(termin_text__icontains=wort)
            | Q(von__icontains=wort)
        )
    if request.GET.get("pdf"):
        doc = Pdf("Streichungsliste", f"Stand {timezone.localtime():%d.%m.%Y %H:%M}")
        doc.tabelle(["Gestrichen am", "Antrag", "Name", "Letzter Termin", "Wie"],
                    [[f"{timezone.localtime(s.gestrichen_am):%d.%m.%Y}", s.antragsnummer, s.name,
                      s.termin_text, s.get_weg_display()] for s in eintraege],
                    breiten=[0.15, 0.1, 0.35, 0.25, 0.15])  # fmt: skip
        return pdf_antwort(doc.erzeugen(), "streichungsliste.pdf")
    return render(request, "warteliste/streichungsliste.html", {
        "eintraege": eintraege, "tage": WartelisteEinstellungen.laden().streichungsliste_tage,
        "q": q,
    })  # fmt: skip


# ── Einstellungen ────────────────────────────────────────────────────────────


@never_cache
@rollen.recht_erforderlich("einstellungen.warteliste")
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=WartelisteEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("warteliste:einstellungen")
    beispiel_antrag = Antrag(vorname="Erika", nachname="Musterfrau")
    beispiel_termin = Termin(datum=timezone.localdate(), von=timezone.localtime().time()
                             .replace(hour=10, minute=0, second=0, microsecond=0))  # fmt: skip
    betreff, text, _ = ablauf.mail_inhalt(beispiel_antrag, beispiel_termin)
    return render(request, "warteliste/einstellungen.html", {
        "form": form, "vorschau_betreff": betreff, "vorschau_text": text,
    })  # fmt: skip
