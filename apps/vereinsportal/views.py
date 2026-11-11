from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.core import listenexport, mail, papierkorb, privatdateien
from apps.core.pdf import im_fenster, pdf_antwort
from apps.konten import rollen
from apps.konten.views import nicht_in_demo
from apps.vereinsportal import auswertung, einlesen
from apps.vereinsportal import briefe as brief
from apps.vereinsportal.forms import (
    BriefForm,
    EinstellungenForm,
    FinanzexportForm,
    SpenderlisteForm,
)
from apps.vereinsportal.models import Beleg, Kontakt, PortalEinstellungen, Sammelbescheinigung

nutzen = rollen.recht_erforderlich("vereinsportal.nutzen")
GRUPPEN = dict(auswertung.GRUPPEN)


def _jahr(request) -> int:
    jahre = auswertung.jahre()
    wahl = request.GET.get("jahr") or request.POST.get("jahr") or ""
    return int(wahl) if wahl.isdigit() and int(wahl) in jahre else jahre[0]


def _finanzexport(request, datei) -> None:
    if datei.name.lower().endswith(".xlsx"):
        e = einlesen.uebersicht_einlesen(datei.read())
    else:
        e = einlesen.finanzexport_einlesen(datei, request.user.get_username())
    teile = [f"{e.neu} neue Belege eingelesen", f"{e.doppelt} waren schon vorhanden"]
    if e.ohne_anschrift:
        teile.append(f"{e.ohne_anschrift} ohne vollständige Anschrift ausgelassen")
    teile.append(
        f"{e.versendet} als im Vereinsportal versendet vermerkt" if e.mit_uebersicht
        else "keine Übersicht der versendeten Belege in der Datei gefunden"
    )  # fmt: skip
    messages.success(request, ", ".join(teile) + ".")


def _spenderliste(request, datei) -> None:
    anzahl, ohne_mail = einlesen.spenderliste_einlesen(datei.read())
    zusatz = f" {ohne_mail} Zeilen ohne gültige E-Mail ausgelassen." if ohne_mail else ""
    messages.success(request, f"Liste ersetzt: {anzahl} Spender mit E-Mail.{zusatz}")


@never_cache
@nutzen
def start(request):
    """Einlesen und die Spender des Jahres nach Gruppen."""
    jahr = _jahr(request)
    if request.method == "POST":
        formulare = {"finanzexport": (FinanzexportForm, _finanzexport),
                     "spenderliste": (SpenderlisteForm, _spenderliste)}  # fmt: skip
        feld = "spenderliste" if "spenderliste" in request.FILES else "finanzexport"
        klasse, einlesen_mit = formulare[feld]
        form = klasse(request.POST, request.FILES)
        if form.is_valid():
            try:
                einlesen_mit(request, form.cleaned_data[feld])
            except einlesen.EinleseFehler as fehler:
                messages.error(request, str(fehler))
        else:
            messages.error(request, "Bitte eine Datei wählen.")
        return redirect(f"{reverse('vereinsportal:start')}?jahr={jahr}")
    alle = auswertung.spender(jahr)
    gruppe = request.GET.get("gruppe") if request.GET.get("gruppe") in GRUPPEN else ""
    return render(request, "vereinsportal/start.html", {
        "jahr": jahr, "jahre": auswertung.jahre(), "gruppe": gruppe,
        "zahlen": auswertung.zahlen(alle),
        "spender": [s for s in alle if not gruppe or s.gruppe == gruppe],
        "belege": Beleg.objects.filter(jahr=jahr).count(),
        "kontakte": Kontakt.objects.count(),
        "finanzexport": FinanzexportForm(), "spenderliste": SpenderlisteForm(),
        "gruppen": auswertung.GRUPPEN,
    })  # fmt: skip


@never_cache
@nutzen
def export(request):
    jahr = _jahr(request)
    gruppe = request.GET.get("gruppe") if request.GET.get("gruppe") in GRUPPEN else ""
    liste = [s for s in auswertung.spender(jahr) if not gruppe or s.gruppe == gruppe]
    titel = f"{GRUPPEN.get(gruppe, 'Spender aus dem Vereinsportal')} {jahr}"
    return listenexport.ausliefern(
        request,
        titel,
        f"spender-{gruppe or 'alle'}-{jahr}",
        auswertung.csv_text(liste),
        weiter=f"{reverse('vereinsportal:start')}?jahr={jahr}",
    )


@never_cache
@nutzen
def beleg(request, pk):
    b = get_object_or_404(Beleg, pk=pk)
    inhalt = privatdateien.lesen(Beleg.ORDNER, b.datei)
    if inhalt is None:
        raise Http404("Datei nicht mehr lesbar.")
    return pdf_antwort(inhalt, b.dateiname)


@never_cache
@nutzen
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=PortalEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("vereinsportal:einstellungen")
    return render(request, "vereinsportal/einstellungen.html", {"form": form})


# --- Dankesbriefe ------------------------------------------------------------------------------


def _allgemein(jahr):
    from apps.serienbriefe.views import _allgemein as allgemein

    return allgemein(jahr)


@im_fenster
@never_cache
@nutzen
def briefe(request):
    """Dankesbriefe einer Gruppe: Vorschau, dann Druck-PDF oder Mails."""
    form = BriefForm(request.POST or None, jahre=auswertung.jahre(),
                     initial={"jahr": _jahr(request)})  # fmt: skip
    kontext = {"form": form, "mail_bereit": mail.eingerichtet()}
    if not (request.method == "POST" and form.is_valid()):
        return render(request, "vereinsportal/briefe.html", kontext)
    d = form.cleaned_data
    alle = brief.auswahl(d["jahr"], d["gruppe"])
    bereit = [s for s in alle if brief.bereit(s)]
    per_mail = d["gruppe"].endswith("_mail")
    schritt = request.POST.get("schritt", "vorschau")
    if schritt == "pdf" and bereit and not per_mail:
        inhalt, warnungen = brief.druck_pdf(bereit, d["vorlage"], d["jahr"],
                                            _allgemein(d["jahr"]))  # fmt: skip
        brief.vermerken(bereit, "brief")
        for w in warnungen[:10]:
            messages.warning(request, w)
        return pdf_antwort(inhalt, f"dankesbriefe-{d['jahr']}-{timezone.localdate():%Y-%m-%d}.pdf")
    if schritt == "senden" and bereit and per_mail:
        return _senden(request, form, bereit)
    kontext |= {"spender": alle, "bereit": bereit, "per_mail": per_mail, "d": d,
                "fehlt": len(alle) - len(bereit)}  # fmt: skip
    return render(request, "vereinsportal/briefe.html", kontext)


@nicht_in_demo
def _senden(request, form, liste):
    from apps.serienbriefe import gestaltung

    d = form.cleaned_data
    allgemein, gesendet, fehler = _allgemein(d["jahr"]), [], []
    for s in liste:
        anhaenge = [(n, inhalt, "application/pdf") for n, inhalt in brief.anlagen(s)]
        try:
            betreff, text, html = gestaltung.mail(d["vorlage"], brief.werte(s, d["jahr"]),
                                                  allgemein)  # fmt: skip
            mail.senden(betreff, text, [s.email], html=html, anhaenge=anhaenge, art="spenden")
        except mail.MailFehler as grund:
            fehler.append(f"{s.name}: {grund}")
            if len(fehler) >= 3 and not gesendet:
                break
        else:
            gesendet.append(s)
    if gesendet:
        brief.vermerken(gesendet, "mail")
        n = len(gesendet)
        messages.success(request, f"{n} Dankesbrief{'e' if n != 1 else ''} per E-Mail gesendet.")
    for f in fehler[:10]:
        messages.error(request, f"Nicht gesendet: {f}")
    return redirect(f"{reverse('vereinsportal:briefe')}?jahr={d['jahr']}")


@never_cache
@nutzen
def sammel(request):
    """Sammelbescheinigungen hochladen und Mehrfachspendern zuordnen."""
    jahr = _jahr(request)
    namen = brief.mehrfachspender(jahr)
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "hochladen":
            zugeordnet, offen = 0, 0
            for datei in request.FILES.getlist("dateien")[:200]:
                try:
                    neu = brief.hochladen(datei, jahr, request.user.get_username())
                except privatdateien.DateiFehler as fehler:
                    messages.error(request, f"{datei.name}: {fehler}")
                    continue
                zugeordnet, offen = (zugeordnet + bool(neu.such_name), offen + (not neu.such_name))
            if zugeordnet or offen:
                messages.success(request, f"{zugeordnet} über den Namen zugeordnet, {offen} bitte "
                                          "von Hand zuordnen.")  # fmt: skip
        elif aktion == "zuordnen":
            eintrag = get_object_or_404(Sammelbescheinigung, pk=request.POST.get("eintrag"))
            name = request.POST.get("name") or ""
            if name in namen:
                brief.zuweisen(eintrag, name)
                messages.success(request, f"„{eintrag.dateiname}“ {name} zugeordnet.")
        elif aktion == "loeschen":
            eintrag = get_object_or_404(Sammelbescheinigung, pk=request.POST.get("eintrag"))
            papierkorb.loeschen(request.user, "Sammelbescheinigung", eintrag.dateiname, eintrag,
                                recht="vereinsportal.nutzen")  # fmt: skip
            messages.success(request, f"„{eintrag.dateiname}“ in den Papierkorb gelegt.")
        return redirect(f"{reverse('vereinsportal:sammel')}?jahr={jahr}")
    alle = Sammelbescheinigung.objects.filter(jahr=jahr)
    vorhanden = set(alle.values_list("name", flat=True))
    return render(request, "vereinsportal/sammel.html", {
        "jahr": jahr, "jahre": auswertung.jahre(), "namen": namen,
        "offen": alle.filter(such_name=""), "zugeordnet": alle.exclude(such_name=""),
        "ohne": [n for n in namen if n not in vorhanden],
    })  # fmt: skip


@never_cache
@nutzen
def sammel_datei(request, pk):
    eintrag = get_object_or_404(Sammelbescheinigung, pk=pk)
    inhalt = privatdateien.lesen(Sammelbescheinigung.ORDNER, eintrag.datei)
    if inhalt is None:
        raise Http404("Datei nicht mehr lesbar.")
    return pdf_antwort(inhalt, brief.dateiname(eintrag.dateiname))
