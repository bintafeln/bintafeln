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
class Empfaengerwahl:
    """Mail an eine Gruppe: Wer sie bekommt, stellt die Tafel zentral unter „Einstellungen →
    Mail-Empfänger“ ein (ADR 0125). ``berechtigte()`` liefert die Konten, die zur Wahl stehen;
    ``leer`` sagt, wer die Mail ohne Auswahl bekommt. Ohne ``lesen``/``speichern`` liegt die
    Auswahl in ``MailEmpfaenger``; bestehende Felder (Anträge, Fahrdienst) geben beide an."""

    # None: keine Auswahl von Personen, nur „wie vorgesehen“ oder niemand
    berechtigte: Callable | None
    leer: str
    lesen: Callable | None = None
    speichern: Callable | None = None
    # False: Die Vorgabe hängt vom Einzelfall ab (z. B. Teamleitung des betroffenen Tages); die
    # Stelle, die die Mail auslöst, übergibt sie an ``an(kennung, vorgabe)``.
    fest: bool = True


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
    # Für die Übersicht „Mail-Empfänger“: wann die Mail kommt, an wen (fester Empfängerkreis)
    # oder die Auswahl der Empfänger
    wann: str = ""
    an: str = ""
    wahl: Empfaengerwahl | None = None


def mit_recht(*codes: str, ohne_stellen: bool = False) -> list:
    """Aktive Konten mit E-Mail und einem der Rechte ``codes``; ``ohne_stellen``: keine
    Ausgabestellen-Konten."""
    from django.contrib.auth import get_user_model

    from apps.konten import rollen

    konten = get_user_model().objects.filter(is_active=True).exclude(email="")
    if ohne_stellen:
        konten = konten.filter(stelle__isnull=True)
    konten = konten.order_by("last_name", "first_name", "username")
    return [k for k in konten if any(rollen.hat_recht(k, c) for c in codes)]


def gewaehlt(art: "Art") -> set[int]:
    """Die für diese Mail ausgewählten Konten (Schlüssel); leer = keine Auswahl getroffen."""
    if art.wahl and art.wahl.lesen:
        return set(art.wahl.lesen())
    from apps.core.models import MailEmpfaenger

    eintrag = MailEmpfaenger.objects.filter(art=art.kennung).first()
    return set(eintrag.personen.values_list("pk", flat=True)) if eintrag else set()


VORGABE = "vorgabe"  # Wert des Eintrags „wie vorgesehen“ in der Auswahl


def hat_vorgabe(art: "Art") -> bool:
    """Gibt es für diese Mail vorgesehene Empfänger (alle Berechtigten, Teamleitung …)? Beim
    neuen Antrag nicht: Dort bekommt die Mail nur, wer ausgewählt ist."""
    return art.wahl.leer != "niemand"


def vorgabe(art: "Art") -> bool:
    """Geht die Mail an die vorgesehenen Empfänger? Solange die Tafel nichts eingestellt hat:
    ja, wenn niemand ausgewählt ist (so war es vor der Auswahl „wie vorgesehen“)."""
    if not hat_vorgabe(art):
        return False
    from apps.core.models import MailEmpfaenger

    eintrag = MailEmpfaenger.objects.filter(art=art.kennung).first()
    return eintrag.vorgabe if eintrag else not gewaehlt(art)


def vorgabe_speichern(art: "Art", wert: bool) -> None:
    from apps.core.models import MailEmpfaenger

    eintrag, _ = MailEmpfaenger.objects.get_or_create(art=art.kennung)
    if eintrag.vorgabe != wert:
        eintrag.vorgabe = wert
        eintrag.save(update_fields=["vorgabe"])


def wahl_speichern(art: "Art", konten) -> None:
    if art.wahl.speichern:
        art.wahl.speichern(konten)
        return
    from apps.core.models import MailEmpfaenger

    eintrag, _ = MailEmpfaenger.objects.get_or_create(art=art.kennung)
    eintrag.personen.set(konten)


def _ausgewaehlte(art: "Art") -> tuple[list, bool]:
    """(ausgewählte Konten, die die Mail noch bekommen dürfen; ob überhaupt jemand ausgewählt
    war). Zentrale Ablage: nur Berechtigte; eigene Ablage (Anträge, Fahrdienst): aktive Konten
    mit E-Mail."""
    wahl = gewaehlt(art)
    if not wahl or art.wahl.berechtigte is None:
        return [], False
    if not art.wahl.lesen:
        return [k for k in art.wahl.berechtigte() if k.pk in wahl], True
    from django.contrib.auth import get_user_model

    konten = get_user_model().objects.filter(pk__in=wahl, is_active=True).exclude(email="")
    return list(konten.order_by("last_name", "first_name", "username")), True


def _mit_vorgabe(art: "Art") -> tuple[list, bool]:
    """(ausgewählte Konten, ob zusätzlich die vorgesehenen Empfänger die Mail bekommen). Sind
    alle Ausgewählten gesperrt oder ohne Recht, gilt wieder die Vorgabe – eine Mail geht nicht
    unbemerkt ins Leere. Ist gar nichts gewählt, bekommt sie niemand."""
    konten, gewaehlt_ = _ausgewaehlte(art)
    return konten, vorgabe(art) or (gewaehlt_ and not konten and hat_vorgabe(art))


def aktuelle(art: "Art") -> list:
    """Wer die Mail im Moment bekommt, soweit es sich ohne den Einzelfall sagen lässt: die
    ausgewählten Personen, dazu – bei „wie vorgesehen“ und fester Vorgabe – alle Berechtigten."""
    konten, mit = _mit_vorgabe(art)
    if mit and art.wahl.fest and art.wahl.berechtigte:
        gesehen = {k.pk for k in konten}
        konten = konten + [k for k in art.wahl.berechtigte() if k.pk not in gesehen]
    return konten


def an(kennung: str, vorgesehen) -> list[str]:
    """Mailadressen für eine Mail, deren Vorgabe vom Einzelfall abhängt (``fest=False``): die
    unter „Mail-Empfänger“ ausgewählten Personen, dazu – bei „wie vorgesehen“ – ``vorgesehen``.
    Ist nichts von beidem gewählt, bekommt sie niemand."""
    vorgesehen = set(vorgesehen)
    art = arten().get(kennung)
    if art is None or art.wahl is None:
        return sorted(vorgesehen)
    konten, mit = _mit_vorgabe(art)
    return sorted({k.email for k in konten} | (vorgesehen if mit else set()))


def empfaenger(kennung: str) -> list[str]:
    """Mailadressen für eine Gruppen-Mail mit Auswahl der Empfänger (siehe ``aktuelle``)."""
    return sorted({k.email for k in aktuelle(arten()[kennung])})


def _recht(code):
    def pruefen(benutzer):
        from apps.konten import rollen

        return rollen.hat_recht(benutzer, code)

    return pruefen


def _antrag_offen(schluessel: str) -> bool:
    from apps.antraege.models import Antrag

    return Antrag.objects.filter(pk=schluessel or 0, status=Antrag.Status.NEU).exists()


def _antrag_lesen():
    from apps.antraege.models import AntragEinstellungen

    return AntragEinstellungen.laden().benachrichtigen.values_list("pk", flat=True)


def _antrag_speichern(konten) -> None:
    from apps.antraege.models import AntragEinstellungen

    AntragEinstellungen.laden().benachrichtigen.set(konten)


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
        fuer=_antrag_fuer, offen=_antrag_offen,
        wann="Sobald jemand das Antragsformular abgeschickt hat.",
        wahl=Empfaengerwahl(lambda: mit_recht("antraege.sehen", ohne_stellen=True), "niemand",
                            _antrag_lesen, _antrag_speichern)),
    Art("korrekturwunsch", "Korrekturwunsch vom Einlass",
        "Entfällt, wenn der Wunsch bis zum Versand entschieden wurde.",
        fuer=_recht("korrekturen.entscheiden"), offen=_korrektur_offen,
        wann="Sobald am Einlass um die Rücknahme einer Abholung, Zahlung oder Teilnahme "
             "gebeten wird.",
        wahl=Empfaengerwahl(lambda: mit_recht("korrekturen.entscheiden"),
                            "alle, die Korrekturwünsche entscheiden dürfen")),
    Art("sicherheitsupdate", "Sicherheitsupdate verfügbar",
        "Die einzelne Person kann sie nicht abschalten, höchstens täglich sammeln.",
        fuer=_recht("system.update"), nie_erlaubt=False,
        wann="Einmal je Sicherheitsupdate, sobald bintafeln davon erfährt.",
        wahl=Empfaengerwahl(lambda: mit_recht("system.update"),
                            "alle, die das Programm aktualisieren dürfen")),
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
            mail.senden(betreff, text, sofort, art="benachrichtigung")
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
                        [benutzer.email], art="benachrichtigung")  # fmt: skip
        except mail.MailFehler as fehler:
            log.warning("Gesammelte Benachrichtigung an %s nicht gesendet: %s", benutzer, fehler)
            behalten |= {m.pk for m in liste}  # beim nächsten Lauf noch einmal
            continue
        gesendet += 1
    # Verschickt, inzwischen erledigt oder ohne Empfänger: weg (Datensparsamkeit)
    Meldung.objects.filter(pk__in=[m.pk for m in faellig if m.pk not in behalten]).delete()
    return gesendet
