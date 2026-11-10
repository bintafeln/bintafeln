"""Archiv „Gesendete Mails“ (ADR 0124): nachlesen, was das Programm wann an wen geschickt hat."""

from auditlog.models import LogEntry
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache

from apps.core import mail
from apps.core.models import GesendeteMail, MailEinstellungen
from apps.konten import rollen

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
