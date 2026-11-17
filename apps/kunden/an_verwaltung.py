"""Nachrichten einer Ausgabestelle an die Verwaltung ohne Bezug zu einem Kunden (ADR 0140).

Die Ausgabestelle schreibt über die Startseite; die Nachricht geht per Mail an die E-Mail der
Tafel (oder an die unter „Mail-Empfänger“ gewählten Personen). Die Verwaltung antwortet auf der
Seite „Nachrichten der Ausgabestellen“; die Antwort steht auf der Startseite der Ausgabestelle,
bis dort jemand „gelesen“ klickt.
"""

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.kunden.models import StellenNachricht

ART = "nachricht_verwaltung"  # Benachrichtigung (apps/core/benachrichtigung.py)


def _name(benutzer) -> str:
    return (benutzer.get_full_name() or benutzer.get_username())[:150]


def schreiben(stelle, benutzer, betreff: str, text: str, basis: str = "") -> StellenNachricht:
    """Neue Nachricht speichern und die Verwaltung per Mail benachrichtigen."""
    from apps.core import benachrichtigung
    from apps.core.models import TafelEinstellungen

    n = StellenNachricht.objects.create(stelle=stelle, von=_name(benutzer), benutzer=benutzer,
                                        betreff=betreff.strip()[:200],
                                        text=text.strip()[:2000])  # fmt: skip
    tafel = TafelEinstellungen.laden().email
    an = benachrichtigung.an(ART, [tafel] if tafel else [])
    wer = f"{n.von} ({stelle.name})" if stelle else n.von
    link = f"{basis}{reverse('kunden:nachrichten')}?anliegen=allgemein" if basis else ""
    mailtext = (f"Nachricht von {wer}:\n\n{n.betreff}\n\n{n.text}"
                + (f"\n\nAntworten in bintafeln: {link}" if link else ""))  # fmt: skip
    betreff_mail = f"Nachricht von {stelle.name if stelle else n.von}: {n.betreff}"
    transaction.on_commit(lambda: benachrichtigung.melden(ART, an, betreff_mail, mailtext,
                                                          schluessel=n.pk))  # fmt: skip
    return n


def offen(schluessel: str) -> bool:
    """Für gesammelte Benachrichtigungen: Ist die Nachricht noch nicht erledigt?"""
    return StellenNachricht.objects.filter(pk=schluessel or 0, erledigt_am__isnull=True).exists()


def antworten(n: StellenNachricht, text: str, benutzer) -> None:
    """Antwort der Verwaltung; die Nachricht ist damit erledigt, die Antwort wartet auf der
    Startseite der Ausgabestelle."""
    jetzt = timezone.now()
    n.antwort = text.strip()[:2000]
    n.antwort_von = _name(benutzer)
    n.beantwortet_am = n.erledigt_am = jetzt
    n.erledigt_von = benutzer.get_username()[:150]
    n.gelesen_am, n.gelesen_von = None, ""
    n.save()


def umschalten(n: StellenNachricht, benutzer) -> None:
    """Ohne Antwort als erledigt markieren bzw. wieder öffnen."""
    if n.erledigt_am:
        n.erledigt_am, n.erledigt_von = None, ""
    else:
        n.erledigt_am, n.erledigt_von = timezone.now(), benutzer.get_username()[:150]
    n.save(update_fields=["erledigt_am", "erledigt_von"])


def antworten_offen(stelle):
    """Ungelesene Antworten der Verwaltung an diese Ausgabestelle (Startseite), älteste zuerst."""
    if stelle is None:
        return StellenNachricht.objects.none()
    return StellenNachricht.objects.filter(
        stelle=stelle, beantwortet_am__isnull=False, gelesen_am__isnull=True
    ).order_by("beantwortet_am")


def gelesen(n: StellenNachricht, benutzer) -> None:
    n.gelesen_am, n.gelesen_von = timezone.now(), _name(benutzer)
    n.save(update_fields=["gelesen_am", "gelesen_von"])


def von_stelle(stelle, anzahl: int = 20):
    """Die letzten Nachrichten dieser Ausgabestelle mit Antworten (Seite zum Schreiben)."""
    if stelle is None:
        return StellenNachricht.objects.none()
    return StellenNachricht.objects.filter(stelle=stelle)[:anzahl]


def offene_anzahl() -> int:
    return StellenNachricht.objects.filter(erledigt_am__isnull=True).count()
