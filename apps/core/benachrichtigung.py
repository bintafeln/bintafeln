"""Benachrichtigungen an Mitarbeitende (ADR 0086): wie oft je Art, Erledigtes entfällt.

Jede Stelle, die Mitarbeitende per Mail auf etwas hinweist (neuer Antrag, Korrekturwunsch,
Ausfall im Dienstplan …), ruft ``melden(art, an, betreff, text, schluessel)`` auf. Jede Person
wählt unter „Mein Konto → Benachrichtigungen“ je Art: sofort, stündlich, täglich oder wöchentlich
gesammelt oder nie (``Art.nie_erlaubt``). Gesammelte Meldungen warten als ``Meldung``; kurz vor
dem Versand fragt ``Art.offen(schluessel)``, ob die Sache noch offen ist – Erledigtes fällt weg.
Adressen ohne Konto (z. B. Helfer ohne Zugang) bekommen die Mail wie bisher sofort.

Den Versand der gesammelten Mails stößt ``python manage.py benachrichtigungen_senden`` an; der
App-Container ruft das alle fünf Minuten auf (docker/entrypoint.sh).
"""

import datetime as dt
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from django.utils import timezone

log = logging.getLogger(__name__)

SOFORT, STUENDLICH, TAEGLICH, WOECHENTLICH, NIE = (
    "sofort", "stuendlich", "taeglich", "woechentlich", "nie",
)  # fmt: skip
HAEUFIGKEITEN = [
    (SOFORT, "sofort"),
    (STUENDLICH, "stündlich gesammelt"),
    (TAEGLICH, "einmal täglich gesammelt"),
    (WOECHENTLICH, "einmal wöchentlich gesammelt"),
    (NIE, "nie"),
]


@dataclass(frozen=True)
class Art:
    kennung: str
    titel: str
    beschreibung: str = ""
    # fuer(benutzer) -> bool: ob die Person diese Art bekommen kann (für „Mein Konto“)
    fuer: Callable | None = None
    # offen(schluessel) -> bool: ist die Sache noch offen? Sonst entfällt die gesammelte Meldung.
    offen: Callable | None = None
    nie_erlaubt: bool = True


def _recht(code):
    def pruefen(benutzer):
        from apps.konten import rollen

        return rollen.hat_recht(benutzer, code)

    return pruefen


def _antrag_offen(schluessel: str) -> bool:
    from apps.antraege.models import Antrag

    return Antrag.objects.filter(pk=schluessel or 0, status=Antrag.Status.NEU,
                                 papierkorb_am__isnull=True).exists()  # fmt: skip


def _antrag_fuer(benutzer) -> bool:
    from apps.antraege.models import AntragEinstellungen

    return AntragEinstellungen.laden().benachrichtigen.filter(pk=benutzer.pk).exists()


def _korrektur_offen(schluessel: str) -> bool:
    from apps.ausgabe.models import Korrekturwunsch

    return Korrekturwunsch.objects.filter(pk=schluessel or 0,
                                          status=Korrekturwunsch.Status.OFFEN).exists()  # fmt: skip


KERN = (
    Art("antrag_neu", "Neuer Antrag eingegangen",
        "Entfällt, wenn der Antrag bis zum Versand bearbeitet wurde.",
        fuer=_antrag_fuer, offen=_antrag_offen),
    Art("korrekturwunsch", "Korrekturwunsch vom Einlass",
        "Entfällt, wenn der Wunsch bis zum Versand entschieden wurde.",
        fuer=_recht("korrekturen.entscheiden"), offen=_korrektur_offen),
    Art("sicherheitsupdate", "Sicherheitsupdate verfügbar",
        "Lässt sich nicht abschalten, höchstens täglich sammeln.",
        fuer=_recht("system.update"), nie_erlaubt=False),
)  # fmt: skip


def arten() -> dict[str, Art]:
    """Alle Arten: Kern und eingeschaltete Module (``Modul.benachrichtigungen``)."""
    from apps.core import module

    alle = {a.kennung: a for a in KERN}
    for m in module.alle():
        if module.aktiv(m.kennung):
            alle.update({a.kennung: a for a in m.benachrichtigungen})
    return alle


def arten_fuer(benutzer) -> list[Art]:
    return [a for a in arten().values() if a.fuer is None or a.fuer(benutzer)]


def wahlmoeglichkeiten(art: Art) -> list[tuple[str, str]]:
    if art.nie_erlaubt:
        return HAEUFIGKEITEN
    return [h for h in HAEUFIGKEITEN if h[0] in (SOFORT, TAEGLICH)]


def haeufigkeit(benutzer, kennung: str) -> str:
    from apps.core.models import BenachrichtigungsWahl

    wahl = BenachrichtigungsWahl.objects.filter(benutzer=benutzer, art=kennung).first()
    return wahl.haeufigkeit if wahl else SOFORT


def faellig_am(benutzer, wie: str, jetzt=None) -> dt.datetime:
    """Wann eine gesammelte Meldung verschickt wird: nächste volle Stunde, nächste Uhrzeit der
    Person (täglich) oder nächster gewählter Wochentag mit Uhrzeit (wöchentlich)."""
    from apps.core.models import BenachrichtigungsZeit

    jetzt = timezone.localtime(jetzt or timezone.now())
    if wie == STUENDLICH:
        return (jetzt + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    zeit = BenachrichtigungsZeit.fuer(benutzer)
    ziel = jetzt.replace(hour=zeit.uhrzeit.hour, minute=zeit.uhrzeit.minute, second=0,
                         microsecond=0)  # fmt: skip
    if wie == WOECHENTLICH:
        ziel += dt.timedelta(days=(zeit.wochentag - ziel.weekday()) % 7)
        if ziel <= jetzt:
            ziel += dt.timedelta(days=7)
    elif ziel <= jetzt:
        ziel += dt.timedelta(days=1)
    return ziel


def melden(art: str, an: Iterable[str], betreff: str, text: str, schluessel="") -> None:
    """Benachrichtigung ``art`` an die Adressen ``an``: je Konto nach dessen Wahl, sonst sofort.
    Fehler beim Mailversand landen im Protokoll; die Sache selbst steht ja im Programm."""
    from django.contrib.auth import get_user_model

    from apps.core import mail
    from apps.core.models import Meldung

    adressen = sorted({a.strip() for a in an if a and a.strip()})
    if not adressen or not mail.eingerichtet():
        return
    konten = {}
    for k in get_user_model().objects.filter(is_active=True, email__in=adressen):
        konten.setdefault(k.email.lower(), k)
    sofort = []
    for adresse in adressen:
        konto = konten.get(adresse.lower())
        wie = haeufigkeit(konto, art) if konto else SOFORT
        if wie == NIE:
            continue
        if wie == SOFORT:
            sofort.append(adresse)
            continue
        Meldung.objects.create(benutzer=konto, art=art, betreff=betreff[:200], text=text,
                               schluessel=str(schluessel)[:100],
                               faellig_am=faellig_am(konto, wie))  # fmt: skip
    if sofort:
        try:
            mail.senden(betreff, text, sofort)
        except mail.MailFehler as fehler:
            log.warning("Benachrichtigung %s nicht gesendet: %s", art, fehler)


def senden(jetzt=None) -> int:
    """Fällige gesammelte Meldungen: je Person eine Mail mit allem, was noch offen ist.
    Ergebnis: Anzahl der verschickten Mails."""
    from apps.core import mail
    from apps.core.models import Meldung, TafelEinstellungen

    jetzt = jetzt or timezone.now()
    faellig = list(Meldung.objects.filter(faellig_am__lte=jetzt).select_related("benutzer")
                   .order_by("benutzer_id", "erstellt_am"))  # fmt: skip
    if not faellig or not mail.eingerichtet():
        return 0
    bekannt = arten()
    je_person: dict = {}
    for m in faellig:
        art = bekannt.get(m.art)
        if art and art.offen and m.schluessel and not art.offen(m.schluessel):
            continue  # inzwischen erledigt
        je_person.setdefault(m.benutzer, []).append(m)
    tafel = TafelEinstellungen.laden().name or "bintafeln"
    fuss = ("\n\n—\nWie oft diese Mails kommen, stellen Sie in bintafeln unter "
            "„Mein Konto → Benachrichtigungen“ ein.")  # fmt: skip
    gesendet, behalten = 0, set()
    for benutzer, liste in je_person.items():
        if not benutzer.is_active or not benutzer.email:
            continue  # wird unten verworfen
        teile = [f"■ {bekannt[m.art].titel if m.art in bekannt else m.art}: {m.betreff}\n\n{m.text}"
                 for m in liste]  # fmt: skip
        betreff = (liste[0].betreff if len(liste) == 1
                   else f"{tafel}: {len(liste)} Benachrichtigungen")  # fmt: skip
        try:
            mail.senden(betreff, ("\n\n" + "─" * 30 + "\n\n").join(teile) + fuss,
                        [benutzer.email])  # fmt: skip
        except mail.MailFehler as fehler:
            log.warning("Gesammelte Benachrichtigung an %s nicht gesendet: %s", benutzer, fehler)
            behalten |= {m.pk for m in liste}  # beim nächsten Lauf noch einmal
            continue
        gesendet += 1
    # Verschickt, inzwischen erledigt oder ohne Empfänger: weg (Datensparsamkeit)
    Meldung.objects.filter(pk__in=[m.pk for m in faellig if m.pk not in behalten]).delete()
    return gesendet
