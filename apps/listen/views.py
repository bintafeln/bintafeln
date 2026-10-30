import csv
import io

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from reportlab.lib.pagesizes import A4, landscape

from apps.core import papierkorb
from apps.core.pdf import Pdf, im_fenster, pdf_antwort
from apps.konten import rollen
from apps.kunden.export import waehlbare_tage
from apps.kunden.models import Zugriff
from apps.listen import abfrage, katalog
from apps.listen import spalten as sp
from apps.listen.models import EigeneListe

nutzen = rollen.recht_erforderlich("listen.nutzen")


def _liste(request, kennung) -> katalog.Liste:
    liste = katalog.NACH_KENNUNG.get(kennung)
    if liste is None:
        raise Http404
    if liste.recht and not rollen.hat_recht(request.user, liste.recht):
        raise PermissionDenied("Für diese Liste fehlt Ihnen ein Recht (z. B. Stammdaten sehen).")
    return liste


def _parameter(request, liste) -> QueryDict:
    """Die Werte der Adresszeile; beim ersten Öffnen die Vorgaben der Liste."""
    if request.GET.get("geladen"):
        return request.GET
    p = QueryDict(mutable=True)
    p.update(katalog.vorgaben(liste, timezone.localdate()))
    if liste.basis == "haushalt" and p.get("einkommensart"):
        # Vorgabe wie „rente“ auf die passende Einkommensart der Tafel abbilden
        treffer = [e for e in abfrage.einkommensarten()
                   if p["einkommensart"].casefold() in e.casefold()]  # fmt: skip
        if len(treffer) == 1:
            p["einkommensart"] = treffer[0]
    p.setlist("s", list(liste.spalten))
    p["sort"], p["gruppe"] = liste.sort, liste.gruppe
    if liste.summen:
        p["summen"] = "1"
    p["geladen"] = "1"
    return p


def _sichtbar(request, liste):
    darf = rollen.rechte_von(request.user)
    return [x for x in katalog.LISTEN if not x.recht or x.recht in darf]


def _eigene_listen(request):
    darf = rollen.rechte_von(request.user)
    qs = EigeneListe.objects.filter(Q(benutzer=request.user) | Q(fuer_alle=True))
    return [e for e in qs if (x := katalog.NACH_KENNUNG.get(e.kennung))
            and (not x.recht or x.recht in darf)]  # fmt: skip


@never_cache
@nutzen
def uebersicht(request):
    sichtbar = _sichtbar(request, None)
    return render(request, "listen/uebersicht.html", {
        "bereiche": [(b, [x for x in sichtbar if x.bereich == b]) for b in katalog.BEREICHE],
        "eigene": _eigene_listen(request),
    })  # fmt: skip


def _kopf(p, liste, spalten_) -> list[dict]:
    """Spaltenköpfe mit Sortier-Link (erster Klick aufsteigend, zweiter absteigend)."""
    aktuell = p.get("sort") or liste.sort
    kopf = []
    for s in spalten_:
        neu = p.copy()
        neu["sort"] = f"-{s.schluessel}" if aktuell == s.schluessel else s.schluessel
        richtung = ("auf" if aktuell == s.schluessel else "ab" if aktuell == f"-{s.schluessel}"
                    else "")  # fmt: skip
        # Kundennummer: kurz „Nr.“, die Spalte nur so breit wie fünf Ziffern
        titel = "Nr." if s.schluessel == "kundennummer" else s.titel
        kopf.append({"titel": titel, "abfrage": neu.urlencode(), "richtung": richtung,
                     "schluessel": s.schluessel})  # fmt: skip
    return kopf


@never_cache
@nutzen
def liste(request, kennung):
    liste = _liste(request, kennung)
    p = _parameter(request, liste)
    darf = rollen.rechte_von(request.user)
    ergebnis = abfrage.rechnen(liste, request.user, p)
    gewaehlt = [s.schluessel for s in ergebnis.spalten]
    erlaubte = sp.erlaubte(liste.basis, darf)
    return render(request, "listen/liste.html", {
        "liste": liste, "p": p, "abfrage": p.urlencode(), "e": ergebnis,
        "kopf": _kopf(p, liste, ergebnis.spalten),
        "spalten_wahl": [(s.schluessel, s.titel, s.schluessel in gewaehlt) for s in erlaubte],
        "gruppen_wahl": [(s.schluessel, s.titel) for s in erlaubte],
        "gruppe": p.get("gruppe", ""), "summen": p.get("summen", ""),
        "stellen": abfrage.stellen(request.user), "kundengruppen": abfrage.gruppen(request.user),
        "status_wahl": abfrage.STATUS,
        "tage": waehlbare_tage(abfrage.gruppen(request.user).filter(aktiv=True))
        if "tag" in liste.filter else [],
        "einkommensarten": abfrage.einkommensarten()
        if "einkommensart" in liste.filter else [],
        "nationen": abfrage.staatsangehoerigkeiten(request.user)
        if "staatsangehoerigkeit" in liste.filter else [],
        "darf_teilen": rollen.hat_recht(request.user, "listen.teilen"),
    })  # fmt: skip


def _protokollieren(request, ergebnis) -> None:
    jetzt = timezone.now()
    Zugriff.objects.bulk_create([
        Zugriff(zeitpunkt=jetzt, benutzer=request.user, benutzername=request.user.get_username(),
                kundennummer=nummer, export=True)
        for nummer in sorted(ergebnis.haushalte)
    ])  # fmt: skip


def _beschreibung(liste, p) -> str:
    teile = []
    for name, titel in (("tag", "Ausgabetag"), ("status", "Status"),
                        ("einkommensart", "Einkommensart"),
                        ("staatsangehoerigkeit", "Staatsangehörigkeit"),
                        ("alter_von", "Alter ab"), ("alter_bis", "Alter bis"),
                        ("ausweis_bis", "Ausweis bis"), ("besuch_vor", "nicht gekommen seit"),
                        ("seit_ab", "Kunde seit"), ("personen_ab", "Personen ab"),
                        ("von", "von"), ("bis", "bis")):  # fmt: skip
        if p.get(name):
            teile.append(f"{titel}: {p[name]}")
    return " · ".join(teile)


def _summentabelle(e) -> tuple[list, list]:
    """Nur Gruppen: Kopf und Zeilen (Gruppe, Anzahl, Summen der Zahlenspalten), mit Summe."""
    zahlen = [i for i, s in enumerate(e.spalten) if s.zahl]
    kopf = ["Gruppe", "Anzahl", *[e.spalten[i].titel for i in zahlen]]
    zeilen = [[g["titel"], str(g["anzahl"]), *[g["summen"][i] for i in zahlen]] for g in e.gruppen]
    zeilen.append(["Summe", str(e.anzahl), *[e.summen_zeile[i] for i in zahlen]])
    return kopf, zeilen


def _csv(e, nur_summen: bool, mit_gruppe: bool) -> str:
    puffer = io.StringIO()
    w = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    if nur_summen:
        kopf, zeilen = _summentabelle(e)
        w.writerows([kopf, *zeilen])
    else:
        w.writerow((["Gruppe"] if mit_gruppe else []) + [s.titel for s in e.spalten])
        for g in e.gruppen:
            w.writerows(([g["titel"]] if mit_gruppe else []) + z["zellen"] for z in g["zeilen"])
    return "\ufeff" + puffer.getvalue()  # BOM, damit Excel Umlaute richtig zeigt


def _pdf(liste, p, e, nur_summen: bool) -> bytes:
    menge = "Personen" if liste.basis == "person" else "Haushalte"
    untertitel = [_beschreibung(liste, p), f"{e.anzahl} {menge}",
                  f"Stand {timezone.localdate():%d.%m.%Y}"]  # fmt: skip
    groesse = landscape(A4) if len(e.spalten) > 5 else A4
    doc = Pdf(liste.titel, " · ".join(t for t in untertitel if t), groesse)
    if nur_summen:
        kopf, zeilen = _summentabelle(e)
        doc.tabelle(kopf, zeilen, rechts=range(1, len(kopf)), summe=True)
        return doc.erzeugen()
    rechts = [i for i, s in enumerate(e.spalten) if s.zahl]
    for g in e.gruppen:
        if g["titel"]:
            doc.ueberschrift(f"{g['titel']} ({g['anzahl']})")
        zeilen = [z["zellen"] for z in g["zeilen"]]
        summe = any(g["summen"])
        if summe:
            zeilen.append([t or ("Summe" if i == 0 else "") for i, t in enumerate(g["summen"])])
        doc.tabelle([s.titel for s in e.spalten], zeilen, rechts=rechts, summe=summe)
    return doc.erzeugen()


@im_fenster
@require_POST
@nutzen
def export(request, kennung, art):
    """CSV oder PDF der angehakten Zeilen (keine angehakt: alle). Jeder Export ins Protokoll."""
    if art not in ("csv", "pdf"):
        raise Http404
    liste = _liste(request, kennung)
    p = QueryDict(request.POST.get("abfrage", ""))
    auswahl = {int(x) for x in request.POST.getlist("id") if x.isdigit()} or None
    e = abfrage.rechnen(liste, request.user, p, auswahl=auswahl)
    _protokollieren(request, e)
    name = f"{liste.kennung}-{timezone.localdate():%Y-%m-%d}"
    nur_summen = bool(p.get("summen"))
    if art == "pdf":
        return pdf_antwort(_pdf(liste, p, e, nur_summen), f"{name}.pdf")
    mit_gruppe = any(g["titel"] for g in e.gruppen)
    antwort = HttpResponse(_csv(e, nur_summen, mit_gruppe), content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    return antwort


@require_POST
@nutzen
def speichern(request, kennung):
    liste = _liste(request, kennung)
    titel = request.POST.get("titel", "").strip()[:100] or liste.titel
    fuer_alle = bool(request.POST.get("fuer_alle")) and rollen.hat_recht(
        request.user, "listen.teilen"
    )
    p = QueryDict(request.POST.get("abfrage", ""), mutable=True)
    p.pop("id", None)
    EigeneListe.objects.create(titel=titel, kennung=liste.kennung, parameter=p.urlencode(),
                               benutzer=request.user, fuer_alle=fuer_alle)  # fmt: skip
    messages.success(request, f"Liste „{titel}“ gespeichert. Sie steht unter „Alle Listen“.")
    return redirect(f"{reverse('listen:liste', args=[liste.kennung])}?{p.urlencode()}")


@nutzen
def eigene(request, pk):
    e = get_object_or_404(EigeneListe, pk=pk)
    if e not in _eigene_listen(request):
        raise Http404
    return redirect(f"{reverse('listen:liste', args=[e.kennung])}?{e.parameter}")


@require_POST
@nutzen
def eigene_loeschen(request, pk):
    e = get_object_or_404(EigeneListe, pk=pk)
    if e.benutzer_id != request.user.pk and not rollen.hat_recht(request.user, "listen.teilen"):
        raise PermissionDenied
    # Wiederherstellen darf, wer auch fremde Listen verwaltet (eigene Listen anderer sind privat)
    papierkorb.loeschen(request.user, "Eigene Liste", e.titel, e, recht="listen.teilen")
    messages.success(request, f"Liste „{e.titel}“ in den Papierkorb gelegt.")
    return redirect("listen:uebersicht")
