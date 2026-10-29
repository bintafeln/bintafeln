"""Regeln der Tickets (ADR 0087): wer was sieht, wer benachrichtigt wird, Fristen."""

import datetime as dt

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core import benachrichtigung
from apps.konten import rollen
from apps.tickets.models import Anhang, Kategorie, Kommentar, Ticket, TicketEinstellungen

BEARBEITEN = "tickets.bearbeiten"


def zustaendige(kategorie: Kategorie):
    """Aktive Konten, die zu einer Kategorie benachrichtigt werden (Personen und Rollen)."""
    return get_user_model().objects.filter(
        Q(ticket_kategorien=kategorie) | Q(groups__ticket_kategorien=kategorie), is_active=True,
    ).distinct()  # fmt: skip


def darf_bearbeiten(benutzer, ticket: Ticket) -> bool:
    """Bearbeiten (Status, Zuständig, löschen) darf, wer das Recht hat oder zur Kategorie gehört."""
    return rollen.hat_recht(benutzer, BEARBEITEN) or zustaendige(ticket.kategorie).filter(
        pk=benutzer.pk).exists()  # fmt: skip


def sichtbar(benutzer):
    """Eigene Tickets; dazu alle (mit Recht) bzw. die der eigenen Kategorien."""
    tickets = Ticket.objects.select_related("kategorie", "erstellt_von", "zustaendig")
    if rollen.hat_recht(benutzer, BEARBEITEN):
        return tickets
    eigene_kategorien = Kategorie.objects.filter(
        Q(personen=benutzer) | Q(rollen__in=benutzer.groups.all())).distinct()  # fmt: skip
    return tickets.filter(Q(erstellt_von=benutzer) | Q(kategorie__in=eigene_kategorien)).distinct()


def _link(adresse_basis: str, ticket: Ticket) -> str:
    return f"{adresse_basis}{reverse('tickets:ticket', args=[ticket.pk])}" if adresse_basis else ""


def eroeffnen(benutzer, kategorie, titel, beschreibung, dateien=(), basis: str = "") -> Ticket:
    """Neues Ticket; Fotos/PDFs verschlüsselt ablegen; die Kategorie benachrichtigen."""
    from apps.core import privatdateien

    with transaction.atomic():
        t = Ticket.objects.create(kategorie=kategorie, titel=titel, beschreibung=beschreibung,
                                  erstellt_von=benutzer)  # fmt: skip
        for datei in dateien:
            name = privatdateien.speichern(Anhang.ORDNER, datei)
            Anhang.objects.create(ticket=t, name=datei.name[:150], datei=name,
                                  typ=datei.content_type[:40])  # fmt: skip
    an = [k.email for k in zustaendige(kategorie) if k.email and k != benutzer]
    text = (
        f"Neues Ticket in „{kategorie}“ von {benutzer.get_full_name() or benutzer}:\n\n"
        f"{titel}\n\n{beschreibung}" + (f"\n\nAnsehen: {_link(basis, t)}" if basis else "")
    )
    transaction.on_commit(lambda: benachrichtigung.melden(
        "ticket_neu", an, f"Ticket {t.pk}: {titel}", text, schluessel=t.pk))  # fmt: skip
    return t


def _melder_benachrichtigen(t: Ticket, wer, was: str, basis: str) -> None:
    """Meldende Person (und Zuständige) erfahren von Antworten und Statuswechseln."""
    an = [p.email for p in (t.erstellt_von, t.zustaendig) if p and p.email and p != wer]
    text = f"{was}\n\nTicket: {t.titel}" + (f"\n\nAnsehen: {_link(basis, t)}" if basis else "")
    transaction.on_commit(lambda: benachrichtigung.melden(
        "ticket_antwort", an, f"Ticket {t.pk}: {t.titel}", text, schluessel=t.pk))  # fmt: skip


def kommentieren(t: Ticket, benutzer, text: str, basis: str = "") -> Kommentar:
    k = Kommentar.objects.create(ticket=t, von=benutzer, text=text)
    Ticket.objects.filter(pk=t.pk).update(geaendert_am=timezone.now())
    wer = benutzer.get_full_name() or benutzer
    _melder_benachrichtigen(t, benutzer, f"{wer} schreibt:\n\n{text}", basis)
    return k


def aendern(t: Ticket, benutzer, status: str, zustaendig, basis: str = "") -> bool:
    """Status und Zuständige; meldet Statuswechsel. Ergebnis: ob sich etwas geändert hat."""
    # Stand aus der Datenbank: ein gebundenes ModelForm hat ``t`` schon geändert
    alt = Ticket.objects.values("status", "zustaendig_id").get(pk=t.pk)
    alt_status, alt_zustaendig = alt["status"], alt["zustaendig_id"]
    t.status = status
    t.zustaendig = zustaendig
    t.erledigt_am = timezone.now() if status == Ticket.Status.ERLEDIGT else None
    if (alt_status, alt_zustaendig) == (t.status, t.zustaendig_id):
        return False
    t.save()
    if alt_status != t.status:
        wer = benutzer.get_full_name() or benutzer
        was = f"Status jetzt: {t.get_status_display()} (von {wer})."
        _melder_benachrichtigen(t, benutzer, was, basis)
    return True


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Erledigte Tickets nach der eingestellten Frist löschen (samt verschlüsselter Dateien)."""
    from apps.core import privatdateien

    heute = heute or timezone.localdate()
    grenze = timezone.make_aware(
        dt.datetime.combine(
            heute - dt.timedelta(days=TicketEinstellungen.laden().loeschen_nach_tagen), dt.time.min
        )
    )
    alte = Ticket.objects.filter(status=Ticket.Status.ERLEDIGT, erledigt_am__lt=grenze)
    for a in Anhang.objects.filter(ticket__in=alte):
        privatdateien.loeschen(Anhang.ORDNER, a.datei)
    return alte.delete()[0]


def ticket_offen(schluessel: str) -> bool:
    """Benachrichtigung „neues Ticket“ entfällt, wenn es schon jemand übernommen hat."""
    return Ticket.objects.filter(pk=schluessel or 0, status=Ticket.Status.OFFEN).exists()
