"""Glückwunsch-Mail zum Geburtstag an Mitarbeitende (ADR 0178).

Der Text kommt aus den Serienbriefen: die Vorlage mit der Verwendung „Glückwunsch zum Geburtstag“,
nach dem Tag die mit „nachträglich“ (fehlt sie, die erste). Vor dem Senden steht die fertige Mail
zum Ändern da; ohne „Senden“ geht nichts hinaus. Schreiben darf, wer den Geburtstagsbrief zu allen
Mitarbeitenden bekommt und Serienbriefe verschicken darf – am Tag selbst und bis zu sieben Tage
danach.
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
    ``mail`` = {"adresse", "tag", "ohne_email", "gesendet"}. Nur wo dieses Konto schreiben darf,
    eine Vorlage da ist und der Tag passt; der eigene Geburtstag bleibt ohne."""
    from apps.konten.models import GeburtstagMail

    if not eintraege or not darf(benutzer) or vorlage() is None:
        return eintraege
    gesendet = {(m.adresse_id, m.tag): m for m in GeburtstagMail.objects.filter(
        tag__gte=heute - dt.timedelta(days=TAGE_DANACH)).order_by("am")}  # fmt: skip
    for e in eintraege:
        a, tag = e["adresse"], e[feld]
        if a.konto_id == benutzer.pk or not heute - dt.timedelta(days=TAGE_DANACH) <= tag <= heute:
            continue
        e["mail"] = {"adresse": a.pk, "tag": tag, "ohne_email": not a.email,
                     "gesendet": gesendet.get((a.pk, tag))}  # fmt: skip
    return eintraege


def senden(benutzer, a, tag: dt.date, v, betreff: str, html: str) -> None:
    """Schickt die (vielleicht von Hand geänderte) Mail an das Geburtstagskind, vermerkt sie als
    Versand und merkt für dieses Konto „Gratuliert“. Löst ``mail.MailFehler`` aus."""
    from apps.core import mail
    from apps.konten.models import GeburtstagGruss, GeburtstagMail
    from apps.serienbriefe import gestaltung
    from apps.serienbriefe.models import Versand

    text, ganz, bilder = gestaltung.mail_fertig(v, gestaltung.speichern(html))
    mail.senden(betreff, text, [a.email], html=ganz, art="serienbrief", bilder=bilder)
    name = benutzer.get_full_name() or benutzer.get_username()
    Versand.objects.create(von=benutzer.get_username(), art=Versand.Art.EMAIL, vorlage=v.name,
                           betreff=betreff[:200], auswahl="Glückwunsch zum Geburtstag",
                           anzahl=1, empfaenger=[f"a:{a.pk}"])  # fmt: skip
    GeburtstagMail.objects.create(adresse=a, tag=tag, von=name[:150])
    GeburtstagGruss.objects.get_or_create(benutzer=benutzer, adresse=a, tag=tag)
