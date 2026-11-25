"""Glückwunsch-Mail zum Geburtstag an Mitarbeitende (ADR 0178).

Der Text kommt aus den Serienbriefen: die Vorlage mit der Verwendung „Glückwunsch zum Geburtstag“,
nach dem Tag die mit „nachträglich“ (fehlt sie, die erste). Vor dem Senden steht die fertige Mail
zum Ändern da; ohne „Senden“ geht nichts hinaus. Schreiben darf, wer den Geburtstagsbrief zu allen
Mitarbeitenden bekommt und Serienbriefe verschicken darf – am Tag selbst und bis zu sieben Tage
danach. Vor dem Tag lässt sich die Mail vormerken (ADR 0179): Der Server schickt sie am Geburtstag
zur gewählten Uhrzeit und meldet es der Person, die vorgemerkt hat.
"""

import datetime as dt

from apps.konten import geburtstage, rollen

TAGE_DANACH = 7


def darf(benutzer) -> bool:
    return rollen.hat_recht(benutzer, "mitarbeitende.geburtstagsbrief") and rollen.hat_recht(
        benutzer, "serienbriefe.erstellen"
    )


def vorlage(nachtraeglich: bool = False):
    """Die Vorlage für den Glückwunsch; None, solange keine dafür gekennzeichnet ist."""
    from apps.serienbriefe.models import GEBURTSTAG, GEBURTSTAG_NACH, Vorlage

    v = Vorlage.objects.filter(verwendung=GEBURTSTAG_NACH).first() if nachtraeglich else None
    return v or Vorlage.objects.filter(verwendung=GEBURTSTAG).first()


def geburtstagskind(pk: int, tag: dt.date, heute: dt.date):
    """Die Adresse, wenn sie zu einem Mitarbeitenden gehört, der an ``tag`` Geburtstag hat(te) und
    der Tag heute oder höchstens sieben Tage her ist; sonst None."""
    if not heute - dt.timedelta(days=TAGE_DANACH) <= tag <= heute:
        return None
    a = geburtstage._mitarbeitende().filter(pk=pk).first()
    if a is None or geburtstage._dieses_jahr(a.geburtsdatum, tag.year) != tag:
        return None
    return a


def entwurf(a, tag: dt.date, heute: dt.date):
    """(Vorlage, Betreff, HTML) mit eingesetzten Feldern – der Vorschlag vor dem Senden; None
    ohne Vorlage."""
    from apps.serienbriefe import empfaenger as emp
    from apps.serienbriefe import gestaltung

    v = vorlage(nachtraeglich=tag < heute)
    if v is None:
        return None
    e = emp.aus_adresse(a, tag.year, alter=str(tag.year - a.geburtsdatum.year))
    return (v, *gestaltung.brief(v, e, emp.allgemein(tag.year)))


def ergaenzen(benutzer, eintraege: list[dict], heute: dt.date, feld: str = "tag") -> list[dict]:
    """Hängt an die Einträge des Geburtstagsbriefs oder -kalenders, was zur Mail gilt:
    ``mail`` = {"adresse", "tag", "ohne_email", "gesendet", "kuenftig", "vorgemerkt"}. Nur wo
    dieses Konto schreiben darf und eine Vorlage da ist; heute und bis sieben Tage danach zum
    Senden, davor zum Vormerken. Der eigene Geburtstag bleibt ohne."""
    from apps.konten.models import GeburtstagMail, GeburtstagVormerkung

    if not eintraege or not darf(benutzer) or vorlage() is None:
        return eintraege
    ab = heute - dt.timedelta(days=TAGE_DANACH)
    gesendet = {(m.adresse_id, m.tag): m for m in GeburtstagMail.objects.filter(
        tag__gte=ab).order_by("am")}  # fmt: skip
    vorgemerkt = {(m.adresse_id, m.tag): m for m in GeburtstagVormerkung.objects.filter(
        tag__gte=ab)}  # fmt: skip
    for e in eintraege:
        a, tag = e["adresse"], e[feld]
        if a.konto_id == benutzer.pk or tag < ab:
            continue
        e["mail"] = {"adresse": a.pk, "tag": tag, "ohne_email": not a.email,
                     "gesendet": gesendet.get((a.pk, tag)), "kuenftig": tag > heute,
                     "vorgemerkt": vorgemerkt.get((a.pk, tag))}  # fmt: skip
    return eintraege


# --- Vormerken: vorbereiten, der Server schickt am Geburtstag (ADR 0179) -------------------------

UHRZEIT = dt.time(8, 0)  # Vorschlag, solange das Konto noch nichts vorgemerkt hat
VORAUS_TAGE = 366


def vormerkbar(pk: int, tag: dt.date, heute: dt.date):
    """Die Adresse, wenn sie zu einem Mitarbeitenden gehört, der an ``tag`` Geburtstag hat, und
    der Tag in der Zukunft liegt (höchstens ein Jahr); sonst None."""
    if not heute < tag <= heute + dt.timedelta(days=VORAUS_TAGE):
        return None
    a = geburtstage._mitarbeitende().filter(pk=pk).first()
    if a is None or geburtstage._dieses_jahr(a.geburtsdatum, tag.year) != tag:
        return None
    return a


def vormerkung(a, tag: dt.date):
    from apps.konten.models import GeburtstagVormerkung

    return GeburtstagVormerkung.objects.filter(adresse=a, tag=tag).first()


def uhrzeit_vorschlag(benutzer) -> dt.time:
    """Die Uhrzeit, die dieses Konto zuletzt gewählt hat, sonst 8 Uhr."""
    from apps.konten.models import GeburtstagVormerkung

    letzte = GeburtstagVormerkung.objects.filter(von=benutzer).order_by("-am").first()
    return letzte.uhrzeit if letzte else UHRZEIT


def vormerken(benutzer, a, tag: dt.date, uhrzeit: dt.time, v, betreff: str, html: str):
    """Legt die Vormerkung an oder ändert sie; gesendet wird genau dieser Text."""
    from django.utils import timezone

    from apps.konten.models import GeburtstagVormerkung
    from apps.serienbriefe import gestaltung

    name = benutzer.get_full_name() or benutzer.get_username()
    return GeburtstagVormerkung.objects.update_or_create(adresse=a, tag=tag, defaults={
        "uhrzeit": uhrzeit, "betreff": betreff[:200], "text": gestaltung.speichern(html),
        "vorlage": v, "von": benutzer, "von_name": name[:150], "am": timezone.now(),
        "fehler": "", "gemeldet": False,
    })[0]  # fmt: skip


def _melden(m, betreff: str, text: str) -> None:
    from apps.core import benachrichtigung

    if m.von and m.von.is_active and m.von.email:
        benachrichtigung.melden("geburtstagsmail", [m.von.email], betreff, text,
                                schluessel=f"{m.adresse_id}:{m.tag}")  # fmt: skip


def faellige_senden(jetzt=None) -> int:
    """Schickt die vorgemerkten Glückwünsche, deren Tag heute und deren Uhrzeit erreicht ist
    (läuft alle fünf Minuten). Wer vorgemerkt hat, bekommt danach eine Meldung. Scheitert das
    Senden, wird es am selben Tag weiter versucht; ist der Tag vorbei, kommt einmal eine Meldung,
    und die Mail lässt sich von Hand nachträglich schicken. Liefert die Anzahl gesendeter Mails."""
    from django.utils import timezone

    from apps.core import mail
    from apps.konten.models import GeburtstagVormerkung

    jetzt = timezone.localtime(jetzt) if jetzt else timezone.localtime()
    heute, anzahl = jetzt.date(), 0
    for m in GeburtstagVormerkung.objects.filter(tag__lt=heute, gemeldet=False):
        m.gemeldet = True
        m.save(update_fields=["gemeldet"])
        _melden(
            m,
            f"Glückwunsch an {m.adresse.name} wurde nicht gesendet",
            f"Der vorgemerkte Glückwunsch zum Geburtstag am {m.tag:%d.%m.%Y} an "
            f"{m.adresse.name} konnte nicht gesendet werden"
            + (f": {m.fehler}" if m.fehler else ".")
            + "\n\nIm Geburtstagskalender können Sie ihn nachträglich von Hand schicken.",
        )
    faellig = GeburtstagVormerkung.objects.filter(tag=heute, uhrzeit__lte=jetzt.time())
    for m in faellig.select_related("adresse", "von", "vorlage"):
        a = geburtstagskind(m.adresse_id, m.tag, heute)
        v = m.vorlage or vorlage()
        try:
            if a is None:
                raise mail.MailFehler("Die Person gehört nicht mehr zu den Mitarbeitenden.")
            if not a.email:
                raise mail.MailFehler("Es ist keine E-Mail-Adresse hinterlegt.")
            if v is None:
                raise mail.MailFehler("Die Vorlage gibt es nicht mehr.")
            senden(m.von, a, m.tag, v, m.betreff, m.text, name=m.von_name)
        except mail.MailFehler as grund:
            m.fehler = str(grund)[:300]
            m.save(update_fields=["fehler"])
            continue
        anzahl += 1
        _melden(
            m,
            f"Glückwunsch an {a.name} wurde gesendet",
            f"Ihr vorgemerkter Glückwunsch zum Geburtstag an {a.name} ({a.email}) ist heute "
            f"um {jetzt:%H:%M} Uhr hinausgegangen.\n\nBetreff: {m.betreff}",
        )
        m.delete()
    return anzahl


def senden(benutzer, a, tag: dt.date, v, betreff: str, html: str, name: str = "") -> None:
    """Schickt die (vielleicht von Hand geänderte) Mail an das Geburtstagskind, vermerkt sie als
    Versand und merkt für dieses Konto „Gratuliert“. Löst ``mail.MailFehler`` aus. ``benutzer``
    darf fehlen (vorgemerkte Mail, Konto inzwischen gelöscht); dann steht ``name`` als Absender."""
    from apps.core import mail
    from apps.konten.models import GeburtstagGruss, GeburtstagMail, GeburtstagVormerkung
    from apps.serienbriefe import gestaltung
    from apps.serienbriefe.models import Versand

    text, ganz, bilder = gestaltung.mail_fertig(v, gestaltung.speichern(html))
    mail.senden(betreff, text, [a.email], html=ganz, art="serienbrief", bilder=bilder)
    if benutzer is not None:
        name = benutzer.get_full_name() or benutzer.get_username()
    wer = benutzer.get_username() if benutzer else name[:150]
    Versand.objects.create(von=wer, art=Versand.Art.EMAIL, vorlage=v.name,
                           betreff=betreff[:200], auswahl="Glückwunsch zum Geburtstag",
                           anzahl=1, empfaenger=[f"a:{a.pk}"])  # fmt: skip
    GeburtstagMail.objects.create(adresse=a, tag=tag, von=name[:150])
    if benutzer is not None:
        GeburtstagGruss.objects.get_or_create(benutzer=benutzer, adresse=a, tag=tag)
    GeburtstagVormerkung.objects.filter(adresse=a, tag=tag).delete()  # erledigt
