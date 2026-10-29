"""Tickets (ADR 0087): eröffnen (alle Angemeldeten), ansehen, beantworten, bearbeiten."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import papierkorb, privatdateien
from apps.konten import rollen
from apps.tickets import ablauf
from apps.tickets.forms import (
    BearbeitenForm,
    EinstellungenForm,
    KategorieForm,
    KommentarForm,
    TicketForm,
)
from apps.tickets.models import Anhang, Kategorie, Ticket, TicketEinstellungen

einstellen = rollen.recht_erforderlich("einstellungen.tickets")


def _basis(request) -> str:
    return request.build_absolute_uri("/").rstrip("/")


def _ticket(request, pk) -> Ticket:
    """Ein Ticket, das die Person sehen darf (sonst 404, damit nichts über fremde verrät)."""
    return get_object_or_404(ablauf.sichtbar(request.user), pk=pk)


@never_cache
@login_required
def liste(request):
    status = request.GET.get("status", "offen")
    tickets = ablauf.sichtbar(request.user)
    if status == "offen":
        tickets = tickets.exclude(status=Ticket.Status.ERLEDIGT)
    elif status in Ticket.Status.values:
        tickets = tickets.filter(status=status)
    kategorie = request.GET.get("kategorie", "")
    if kategorie.isdigit():
        tickets = tickets.filter(kategorie_id=kategorie)
    return render(request, "tickets/liste.html", {
        "tickets": tickets, "status": status, "kategorie": kategorie,
        "kategorien": Kategorie.objects.all(), "stati": Ticket.Status.choices,
        "keine_kategorie": not Kategorie.objects.filter(aktiv=True).exists(),
    })  # fmt: skip


@never_cache
@login_required
def neu(request):
    form = TicketForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            t = ablauf.eroeffnen(request.user, d["kategorie"], d["titel"], d["beschreibung"],
                                 d["dateien"], basis=_basis(request))  # fmt: skip
        except privatdateien.DateiFehler as fehler:
            form.add_error("dateien", str(fehler))
        else:
            messages.success(
                request, f"Ticket {t.pk} eröffnet. Die Zuständigen sind benachrichtigt."
            )
            return redirect("tickets:ticket", t.pk)
    return render(request, "tickets/neu.html", {"form": form})


@never_cache
@login_required
def ticket(request, pk):
    t = _ticket(request, pk)
    darf = ablauf.darf_bearbeiten(request.user, t)
    kommentar = KommentarForm(request.POST if "kommentar" in request.POST else None)
    bearbeiten = BearbeitenForm(request.POST if "aendern" in request.POST else None, instance=t)
    if request.method == "POST":
        if "kommentar" in request.POST and kommentar.is_valid():
            ablauf.kommentieren(t, request.user, kommentar.cleaned_data["text"], _basis(request))
            messages.success(request, "Antwort gespeichert.")
            return redirect("tickets:ticket", t.pk)
        if "aendern" in request.POST and darf and bearbeiten.is_valid():
            d = bearbeiten.cleaned_data
            if ablauf.aendern(t, request.user, d["status"], d["zustaendig"], _basis(request)):
                messages.success(request, "Ticket geändert.")
            return redirect("tickets:ticket", t.pk)
        if "aendern" in request.POST and not darf:
            raise Http404
    return render(request, "tickets/ticket.html", {
        "t": t, "darf": darf, "kommentar": kommentar, "bearbeiten": bearbeiten,
        "kommentare": t.kommentare.select_related("von"), "anhaenge": t.anhaenge.all(),
    })  # fmt: skip


@never_cache
@login_required
def anhang(request, pk):
    a = get_object_or_404(Anhang.objects.select_related("ticket"), pk=pk)
    _ticket(request, a.ticket_id)
    inhalt = privatdateien.lesen(Anhang.ORDNER, a.datei)
    if inhalt is None:
        raise Http404("Datei nicht lesbar.")
    antwort = HttpResponse(inhalt, content_type=a.typ or "application/octet-stream")
    antwort["Content-Disposition"] = f'inline; filename="ticket-{a.ticket_id}-{a.pk}"'
    antwort["X-Content-Type-Options"] = "nosniff"
    return antwort


@require_POST
@login_required
def loeschen(request, pk):
    t = _ticket(request, pk)
    if not ablauf.darf_bearbeiten(request.user, t):
        raise Http404
    papierkorb.loeschen(request.user, "Ticket", str(t), t, recht=ablauf.BEARBEITEN)
    messages.success(request, f"{t} liegt im Papierkorb.")
    return redirect("tickets:liste")


@never_cache
@einstellen
def kategorien(request):
    e = TicketEinstellungen.laden()
    form = EinstellungenForm(request.POST or None, instance=e)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("tickets:kategorien")
    return render(request, "tickets/kategorien.html", {
        "kategorien": Kategorie.objects.prefetch_related("personen", "rollen"), "form": form,
    })  # fmt: skip


@never_cache
@einstellen
def kategorie(request, pk=None):
    k = get_object_or_404(Kategorie, pk=pk) if pk else Kategorie()
    form = KategorieForm(request.POST or None, instance=k)
    if request.method == "POST" and form.is_valid():
        k = form.save()
        messages.success(request, f"Kategorie „{k}“ gespeichert.")
        return redirect("tickets:kategorien")
    return render(request, "tickets/kategorie.html", {"form": form, "k": k if pk else None})
