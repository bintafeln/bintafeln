"""Korrekturwünsche vom Einlass (ADR 0035).

Wer am Einlass nicht selbst zurücknehmen darf (Recht ``einlass.zuruecknehmen``), bittet mit
einem Grund darum. Entscheiden Admin und alle mit ``korrekturen.entscheiden``; sie bekommen eine
Mail, wenn ein Mailserver eingerichtet ist.
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.ausgabe import konto
from apps.ausgabe.models import Buchung, Korrekturwunsch, Teilnahme
from apps.konten import rollen
from apps.kunden.models import Abholung, Haushalt, abholfrist_beginn

Art = Korrekturwunsch.Art


class KorrekturFehler(ValueError):
    pass


def _objekt(art, pk):
    if art == Art.ABHOLUNG:
        return Abholung.objects.select_related("ausgabestelle", "haushalt").filter(pk=pk).first()
    if art == Art.ZAHLUNG:
        return Buchung.objects.filter(pk=pk, art=Buchung.Art.EINZAHLUNG).first()
    return Teilnahme.objects.select_related("aktion", "auswahl").filter(pk=pk).first()


def beschreiben(art, obj) -> str:
    if art == Art.ABHOLUNG:
        um = f" {obj.uhrzeit:%H:%M}" if obj.uhrzeit else ""
        wo = f", {obj.ausgabestelle.name}" if obj.ausgabestelle else ""
        return f"Abholung am {obj.datum:%d.%m.%Y}{um}{wo}"
    if art == Art.ZAHLUNG:
        wann = timezone.localtime(obj.zeitpunkt)
        return f"Zahlung über {konto.euro(obj.haben)} am {wann:%d.%m.%Y %H:%M}"
    was = f" ({obj.auswahl})" if obj.auswahl else ""
    return f"{obj.aktion}{was}, {obj.menge}× am {timezone.localtime(obj.zeitpunkt):%d.%m.%Y}"


def offene(kundennummer) -> dict[tuple[str, int], Korrekturwunsch]:
    """Offene Wünsche eines Haushalts nach (Art, Datensatz) für die Einlass-Karte."""
    return {(k.art, k.objekt_id): k for k in Korrekturwunsch.objects.filter(
        kundennummer=kundennummer, status=Korrekturwunsch.Status.OFFEN)}  # fmt: skip


TAGE_ANZEIGEN = 14


def entschiedene(kundennummer) -> list[Korrekturwunsch]:
    """Entschiedene Wünsche eines Haushalts der letzten Tage für die Einlass-Karte."""
    seit = timezone.now() - dt.timedelta(days=TAGE_ANZEIGEN)
    wuensche = Korrekturwunsch.objects.filter(kundennummer=kundennummer, entschieden_am__gte=seit)
    return list(wuensche.exclude(status=Korrekturwunsch.Status.OFFEN).order_by("-entschieden_am"))


def empfaenger() -> list[str]:
    """Mailadressen aller aktiven Konten, die Korrekturwünsche entscheiden dürfen."""
    konten = get_user_model().objects.filter(is_active=True).exclude(email="")
    konten = konten.filter(Q(is_superuser=True) | Q(groups__rolle__isnull=False)).distinct()
    return sorted({k.email for k in konten if rollen.hat_recht(k, "korrekturen.entscheiden")})


def beantragen(art, pk, *, grund, anmerkung, von) -> Korrekturwunsch:
    obj = _objekt(art, pk)
    if obj is None:
        raise KorrekturFehler("Diesen Eintrag gibt es nicht mehr.")
    if not grund:
        raise KorrekturFehler("Bitte einen Grund wählen.")
    if art == Art.ABHOLUNG:
        nummer = obj.haushalt.kundennummer
    elif art == Art.ZAHLUNG:
        nummer = obj.kundennummer or (obj.haushalt.kundennummer if obj.haushalt else "")
    else:
        nummer = obj.kundennummer
    if Korrekturwunsch.objects.filter(art=art, objekt_id=pk,
                                      status=Korrekturwunsch.Status.OFFEN).exists():  # fmt: skip
        raise KorrekturFehler("Für diesen Eintrag ist schon ein Korrekturwunsch offen.")
    k = Korrekturwunsch.objects.create(
        art=art, objekt_id=pk, kundennummer=nummer, beschreibung=beschreiben(art, obj)[:200],
        grund=grund[:100], anmerkung=anmerkung.strip()[:300], erstellt_von=von[:150],
    )  # fmt: skip
    transaction.on_commit(lambda: _benachrichtigen(k))
    return k


def _benachrichtigen(k: Korrekturwunsch) -> None:
    from apps.core import mail

    an = empfaenger()
    if not an or not mail.eingerichtet():
        return
    text = (
        f"Am Einlass wurde um eine Korrektur gebeten.\n\nKunde: {k.kundennummer}\n"
        f"Was: {k.beschreibung}\nGrund: {k.grund}\n"
        + (f"Anmerkung: {k.anmerkung}\n" if k.anmerkung else "")
        + f"Von: {k.erstellt_von}\n\nEntscheiden unter „Ausgabe → Korrekturwünsche“."
    )
    from apps.core import benachrichtigung

    # Der Wunsch steht ohnehin auf der Seite; die Mail kommt so oft, wie jede Person es wählt
    benachrichtigung.melden("korrekturwunsch", an, f"Korrekturwunsch für Kunde {k.kundennummer}",
                            text, schluessel=k.pk)  # fmt: skip


def zuruecknehmen(art, obj) -> None:
    """Nimmt eine Abholung, Zahlung oder Teilnahme zurück (auch an späteren Tagen)."""
    with transaction.atomic():
        if art == Art.ABHOLUNG:
            h = obj.haushalt
            konto.abholung_zuruecknehmen(obj)
            letzte = h.abholungen.order_by("-datum").first()
            Haushalt.objects.filter(pk=h.pk).update(letzter_besuch=letzte.datum if letzte else None)
        elif art == Art.ZAHLUNG:
            konto.zuruecknehmen(obj)
        else:
            obj.delete()
        Korrekturwunsch.objects.filter(art=art, objekt_id=obj.pk,
                                       status=Korrekturwunsch.Status.OFFEN).update(
            status=Korrekturwunsch.Status.ZURUECKGENOMMEN, entschieden_am=timezone.now(),
            antwort="direkt zurückgenommen")  # fmt: skip


def entscheiden(k: Korrekturwunsch, *, annehmen: bool, von: str, antwort: str = "") -> str:
    if k.status != Korrekturwunsch.Status.OFFEN:
        raise KorrekturFehler("Dieser Korrekturwunsch ist schon entschieden.")
    meldung = "abgelehnt"
    if annehmen:
        obj = _objekt(k.art, k.objekt_id)
        if obj is None:
            antwort = antwort or "Eintrag gab es nicht mehr."
            meldung = "erledigt – den Eintrag gab es nicht mehr"
        else:
            zuruecknehmen(k.art, obj)
            meldung = "zurückgenommen"
        k.status = Korrekturwunsch.Status.ZURUECKGENOMMEN
    else:
        k.status = Korrekturwunsch.Status.ABGELEHNT
    k.entschieden_am, k.entschieden_von, k.antwort = timezone.now(), von[:150], antwort[:300]
    k.save()
    return meldung


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Entschiedene Wünsche werden so lange aufbewahrt wie Abholungen; offene bleiben."""
    grenze = timezone.make_aware(dt.datetime.combine(abholfrist_beginn(heute), dt.time()))
    return Korrekturwunsch.objects.exclude(status=Korrekturwunsch.Status.OFFEN).filter(
        erstellt_am__lt=grenze).delete()[0]  # fmt: skip
