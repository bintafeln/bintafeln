"""Ansichten des Moduls „Angebote mit Anmeldung“ (ADR 0131): Pflege und Liste für das Büro,
Eintragen am Einlass."""

import csv
from urllib.parse import urlencode

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.angebote import ablauf
from apps.angebote.forms import AngebotForm
from apps.angebote.models import Angebot, Interesse
from apps.ausgabe import stelle as stellen
from apps.core import papierkorb
from apps.core.pdf import Pdf, pdf_antwort
from apps.konten import rollen
from apps.kunden import zugang

verwalten = rollen.recht_erforderlich("angebote.verwalten")
am_einlass = rollen.recht_erforderlich("angebote.eintragen")


def _zum_einlass(kundennummer):
    return redirect(f"{reverse('ausgabe:empfang')}?{urlencode({'nummer': kundennummer})}")


# --- Pflege und Liste (Büro) -------------------------------------------------------------------


@never_cache
@verwalten
def liste(request):
    heute = timezone.localdate()
    angebote = list(Angebot.objects.all())
    for a in angebote:
        a.zahlen = ablauf.zahlen(a)
        a.laeuft = ablauf.laeuft(a, heute)
        a.offen = ablauf.offen(a, heute)
    return render(request, "angebote/liste.html", {"angebote": angebote, "heute": heute})


@never_cache
@verwalten
def bearbeiten(request, pk=None):
    angebot = get_object_or_404(Angebot, pk=pk) if pk else None
    heute = timezone.localdate()
    start = None if angebot else {"anmeldung_von": heute, "plaetze": 12, "hoechstens": 20}
    form = AngebotForm(request.POST or None, instance=angebot, initial=start)
    if request.method == "POST" and form.is_valid():
        angebot = form.save()
        messages.success(request, f"„{angebot}“ gespeichert.")
        return redirect("angebote:angebot", pk=angebot.pk)
    return render(request, "angebote/bearbeiten.html", {"form": form, "angebot": angebot})


@never_cache
@verwalten
def angebot(request, pk):
    a = get_object_or_404(Angebot, pk=pk)
    heute = timezone.localdate()
    return render(request, "angebote/angebot.html", {
        "a": a, "zahlen": ablauf.zahlen(a), "laeuft": ablauf.laeuft(a, heute),
        "offen": ablauf.offen(a, heute), "staende": Interesse.Stand.choices,
        "interessierte": a.interessierte.select_related("ausgabestelle"),
    })  # fmt: skip


@require_POST
@verwalten
def loeschen(request, pk):
    a = get_object_or_404(Angebot, pk=pk)
    papierkorb.loeschen(request.user, "Angebot mit Anmeldung", str(a), a,
                        recht="angebote.verwalten")  # fmt: skip
    messages.success(request, f"„{a}“ in den Papierkorb gelegt.")
    return redirect("angebote:liste")


@require_POST
@verwalten
def plaetze(request, pk):
    a = get_object_or_404(Angebot, pk=pk)
    zugesagt, nach = ablauf.plaetze_vergeben(a)
    messages.success(
        request,
        f"{zugesagt} Plätze zugesagt, {nach} Nachrücker – in der Reihenfolge der Anmeldung. "
        "Einzelne lassen sich ändern.",
    )
    return redirect("angebote:angebot", pk=a.pk)


@require_POST
@verwalten
def schliessen(request, pk):
    a = get_object_or_404(Angebot, pk=pk)
    a.geschlossen = request.POST.get("geschlossen") == "1"
    a.save(update_fields=["geschlossen"])
    messages.success(request, "Anmeldung geschlossen." if a.geschlossen
                     else "Anmeldung wieder geöffnet.")  # fmt: skip
    return redirect("angebote:angebot", pk=a.pk)


@require_POST
@verwalten
def stand(request, pk):
    e = get_object_or_404(Interesse, pk=pk)
    neu = request.POST.get("stand")
    if neu in Interesse.Stand.values:
        e.stand = neu
        e.save(update_fields=["stand"])
    return redirect("angebote:angebot", pk=e.angebot_id)


def _zeilen(a):
    return [
        [nr, e.kundennummer, e.nachname, e.vorname, e.telefon,
         str(e.ausgabestelle or ""), f"{timezone.localtime(e.eingetragen_am):%d.%m.%Y}",
         e.get_stand_display()]
        for nr, e in enumerate(a.interessierte.select_related("ausgabestelle"), start=1)
    ]  # fmt: skip


KOPF = ["Nr.", "Kundennr.", "Nachname", "Vorname", "Telefon", "Ausgabestelle", "Eingetragen",
        "Stand"]  # fmt: skip


@verwalten
def liste_pdf(request, pk):
    a = get_object_or_404(Angebot, pk=pk)
    z = ablauf.zahlen(a)
    doc = Pdf(a.bezeichnung, f"{z['anzahl']} Interessierte, {a.plaetze} Plätze")
    if a.beschreibung:
        doc.absatz(a.beschreibung)
    doc.tabelle(KOPF, [[str(w) for w in zeile] for zeile in _zeilen(a)],
                breiten=[0.06, 0.11, 0.17, 0.15, 0.15, 0.14, 0.11, 0.11])  # fmt: skip
    return pdf_antwort(doc.erzeugen(), f"angebot-{a.pk}-interessierte.pdf")


@verwalten
def liste_csv(request, pk):
    a = get_object_or_404(Angebot, pk=pk)
    antwort = HttpResponse(content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = f'attachment; filename="angebot-{a.pk}-interessierte.csv"'
    antwort.write("﻿")
    schreiber = csv.writer(antwort, delimiter=";")
    schreiber.writerow(KOPF)
    schreiber.writerows(_zeilen(a))
    return antwort


# --- Am Einlass --------------------------------------------------------------------------------


@never_cache
@am_einlass
def eintragen(request, pk, kundennummer):
    """Vom Knopf auf der Einlass-Karte: Personen des Haushalts eintragen. Die Seite zeigt, wer
    noch frei und wer schon eingetragen ist; der Haushalt wird wie überall am Einlass über die
    Zuordnung zur Ausgabestelle geprüft."""
    haushalt = zugang.haushalt(request.user, kundennummer)
    a = get_object_or_404(Angebot, pk=pk)
    heute = timezone.localdate()
    if request.method == "POST" and "person" in request.POST:
        frei = {str(p.pk): p for p in ablauf.noch_frei(a, haushalt)}
        gewaehlt = [frei[pk] for pk in request.POST.getlist("person") if pk in frei]
        eingetragen = []
        for person in gewaehlt:
            try:
                ablauf.eintragen(a, haushalt, person, stelle=stellen.aktuelle(request.user),
                                 von=request.user.get_username(), heute=heute)  # fmt: skip
            except ablauf.AngebotFehler as fehler:
                messages.error(request, str(fehler))
                break
            eingetragen.append(f"{person.vorname} {person.nachname}")
        if eingetragen:
            messages.success(request, f"Für „{a}“ eingetragen: {', '.join(eingetragen)}.")
        return _zum_einlass(kundennummer)
    return render(request, "angebote/eintragen.html", {
        "a": a, "h": haushalt, "frei": ablauf.noch_frei(a, haushalt),
        "da": ablauf.eingetragen(a, kundennummer), "offen": ablauf.offen(a, heute),
        "zahlen": ablauf.zahlen(a),
    })  # fmt: skip


@require_POST
@am_einlass
def austragen(request, pk):
    e = get_object_or_404(Interesse, pk=pk)
    zugang.pruefen_nummer(request.user, e.kundennummer)
    papierkorb.loeschen(request.user, "Interesse an einem Angebot", f"{e.name} – {e.angebot}", e,
                        recht="angebote.verwalten", kundennummer=e.kundennummer)  # fmt: skip
    messages.success(request, f"{e.name} ist bei „{e.angebot}“ ausgetragen.")
    return _zum_einlass(e.kundennummer)
