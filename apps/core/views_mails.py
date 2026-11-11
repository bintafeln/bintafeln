"""Archiv „Gesendete Mails“ (ADR 0124): nachlesen, was das Programm wann an wen geschickt hat."""

from auditlog.models import LogEntry
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from apps.core import benachrichtigung, mail, mailuebersicht
from apps.core.forms import Mehrfachauswahl
from apps.core.models import GesendeteMail, MailEinstellungen
from apps.konten import rollen
from apps.konten.views import nicht_in_demo

JE_SEITE = 50


@never_cache
@rollen.recht_erforderlich("system.mails")
def liste(request):
    q = request.GET.get("q", "").strip()
    art = request.GET.get("art", "")
    nur_fehler = request.GET.get("fehler") == "1"
    mails = GesendeteMail.objects.defer("text")
    if q:
        mails = mails.filter(Q(an__icontains=q) | Q(betreff__icontains=q))
    if art in mail.ARTEN:
        mails = mails.filter(art=art)
    if nur_fehler:
        mails = mails.exclude(fehler="")
    seite = Paginator(mails, JE_SEITE).get_page(request.GET.get("seite"))
    for m in seite:
        m.art_text = mail.ARTEN.get(m.art, "–")
    return render(request, "core/mails.html", {
        "seite": seite, "q": q, "art": art, "nur_fehler": nur_fehler,
        "arten": mail.ARTEN.items(), "tage": MailEinstellungen.laden().archiv_tage,
        "fehler_anzahl": GesendeteMail.objects.exclude(fehler="").count(),
    })  # fmt: skip


@never_cache
@rollen.recht_erforderlich("system.mails")
def ansehen(request, pk):
    m = get_object_or_404(GesendeteMail, pk=pk)
    # Die Mail enthält Personendaten: Der Abruf steht im Änderungsprotokoll (wer, wann, welche)
    LogEntry.objects.log_create(m, force_log=True, action=LogEntry.Action.ACCESS,
                                actor=request.user, changes={})  # fmt: skip
    return render(request, "core/mail.html", {"m": m, "art_text": mail.ARTEN.get(m.art, "–")})


def _name(konto) -> str:
    return f"{konto.get_full_name() or konto.username} ({konto.email})"


class EmpfaengerForm(forms.Form):
    """Je Gruppen-Mail ein Auswahlmenü der Berechtigten. Schon Gewählte bleiben wählbar, auch
    wenn sie das Recht inzwischen nicht mehr haben (sonst fielen sie beim Speichern still weg)."""

    def __init__(self, *args, arten, **kwargs):
        super().__init__(*args, **kwargs)
        self.arten = arten
        konten = get_user_model().objects.order_by("last_name", "first_name", "username")
        for art in arten:
            gewaehlt = benachrichtigung.gewaehlt(art)
            erlaubt = {k.pk for k in art.wahl.berechtigte()} | gewaehlt
            feld = forms.ModelMultipleChoiceField(
                label=art.titel, required=False, queryset=konten.filter(pk__in=erlaubt),
                widget=Mehrfachauswahl(leer=art.wahl.leer), initial=sorted(gewaehlt),
            )  # fmt: skip
            feld.label_from_instance = _name
            self.fields[art.kennung] = feld

    def speichern(self) -> None:
        for art in self.arten:
            benachrichtigung.wahl_speichern(art, self.cleaned_data[art.kennung])


@never_cache
@rollen.recht_erforderlich("einstellungen.mail")
@nicht_in_demo
def empfaenger(request):
    """Wer bekommt welche Mail: alle Mails des Programms mit Anlass und Empfängern; bei Mails an
    eine Gruppe wählt die Tafel hier, wer sie bekommt (ADR 0125)."""
    arten = list(benachrichtigung.arten().values())
    # Eine leere Auswahl ist auch eine Eingabe (alle Häkchen entfernt), deshalb nicht „or None“
    daten = request.POST if request.method == "POST" else None
    form = EmpfaengerForm(daten, arten=[a for a in arten if a.wahl])
    if request.method == "POST" and form.is_valid():
        form.speichern()
        messages.success(request, "Mail-Empfänger gespeichert.")
        return redirect("core:mail_empfaenger")
    zeilen = []
    for art in arten:
        zeile = {"art": art, "feld": form[art.kennung] if art.wahl else None}
        if art.wahl:
            zeile["aktuell"] = [k.get_full_name() or k.username
                                for k in benachrichtigung.aktuelle(art)]  # fmt: skip
        zeilen.append(zeile)
    darf = rollen.rechte_von(request.user)
    return render(request, "core/mail_empfaenger.html", {
        "form": form, "zeilen": zeilen, "weitere": mailuebersicht.alle(darf),
        "darf_archiv": "system.mails" in darf,
    })  # fmt: skip
