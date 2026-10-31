"""Verwaltung der Mitarbeitenden (ADR 0015).

Schutzregeln, die hier und nicht in den Ansichten stehen, damit sie überall gelten:
- Niemand sperrt sich selbst oder nimmt sich selbst die Admin-Rolle.
- Wer nur über die Büro-Freigabe verwaltet, fasst keine Admin-Konten an und vergibt keine
  Admin-Rolle.

Zusammen sorgt das dafür, dass immer mindestens ein aktiver Admin bleibt: Ein Admin-Konto
ändert nur ein aktiver Admin, und der kann sich selbst weder sperren noch herabstufen.
"""

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from apps.konten import rollen

# Ohne leicht verwechselbare Zeichen (0/O, 1/l/I), damit man es gut abschreiben kann.
ZEICHEN = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class VerwaltungsFehler(ValueError):
    pass


def startpasswort() -> str:
    """Zufälliges Passwort in drei Vierergruppen, z. B. 'k7Qm-xP3a-9wTe'."""
    return "-".join("".join(secrets.choice(ZEICHEN) for _ in range(4)) for _ in range(3))


def ist_admin(benutzer) -> bool:
    return rollen.ist_admin(benutzer)


def vergebbare_rollen(verwalter) -> list[str]:
    """Admins vergeben alle Rollen; sonst nur Rollen, deren Rechte man selbst alle hat
    (nie die Rolle Admin). So kann sich niemand über eine Rolle mehr Rechte verschaffen."""
    if rollen.ist_admin(verwalter):
        return [r.name for r in rollen.alle_rollen()]
    eigene = rollen.rechte_von(verwalter)
    return [r.name for r in rollen.alle_rollen() if not r.ist_admin and set(r.rechte) <= eigene]


def darf_bearbeiten(verwalter, ziel) -> bool:
    return rollen.ist_admin(verwalter) or not ist_admin(ziel)


def _rollen_setzen(verwalter, ziel, rollen_namen) -> None:
    """Setzt die vergebbaren Rollen; Rollen, die der Verwalter nicht vergeben darf, bleiben."""
    erlaubt = set(vergebbare_rollen(verwalter))
    behalten = set(ziel.groups.exclude(name__in=erlaubt).values_list("name", flat=True))
    ziel.groups.set(Group.objects.filter(name__in=set(rollen_namen) | behalten))
    rollen.rechte_vergessen(ziel)


def adresse_abgleichen(ziel) -> None:
    """Jedes Mitarbeiter-Konto ist eine Person im Adressbuch (ADR 0097) und ein ehrenamtlicher
    Helfer (im Dienst-/Fahrdienstplan einteilbar). Helfer sind überall tätig – Ausgabe,
    Fahrdienst, Büro, Lager, Sortierung … –, deshalb werden alle Konten als Helfer markiert.
    Konten einer Ausgabestelle (Einlass-Tablet) bleiben außen vor; sie sind keine Person."""
    if ziel.stelle_id:
        return
    from apps.adressen.models import Adresse

    adr = Adresse.objects.filter(konto=ziel).first()
    if adr is None:
        stamm = getattr(ziel, "stammdaten", None)
        adr = Adresse(
            art=Adresse.Art.PERSON, konto=ziel,
            vorname=(ziel.first_name or "")[:100],
            nachname=(ziel.last_name or ziel.get_username())[:100],
            email=ziel.email or "", helfer=True, helfer_aktiv=ziel.is_active,
            anrede=getattr(stamm, "anrede", "") or "",
            strasse=getattr(stamm, "strasse", "") or "",
            plz=getattr(stamm, "plz", "") or "",
            ort=getattr(stamm, "ort", "") or "",
            telefon=getattr(stamm, "telefon", "") or "",
            mobil=getattr(stamm, "handy", "") or "",
        )  # fmt: skip
        adr.save()
    elif not adr.helfer:  # vorhandene Adresse (z. B. aus dem Fahrdienst) als Helfer markieren
        adr.helfer = True
        adr.save(update_fields=["helfer"])


def _pruefen(verwalter, ziel):
    if not darf_bearbeiten(verwalter, ziel):
        raise VerwaltungsFehler("Admin-Konten kann nur ein Admin bearbeiten.")


def _passwort_neu(ziel) -> str:
    passwort = startpasswort()
    ziel.set_password(passwort)
    ziel.passwort_aendern = True
    return passwort


@transaction.atomic
def anlegen(verwalter, daten: dict, rollen_namen: list[str], einladung=False):
    """Legt ein Konto an. Liefert es mit dem Startpasswort (nur einmal anzeigen) oder – bei
    Einladung per Mail – mit None; das Passwort setzt die Person dann selbst über den Link."""
    if set(rollen_namen) - set(vergebbare_rollen(verwalter)):
        raise VerwaltungsFehler("Diese Rolle dürfen Sie nicht vergeben.")
    ziel = get_user_model()(**daten)
    if einladung:
        ziel.set_unusable_password()
        passwort = None
    else:
        passwort = _passwort_neu(ziel)
    ziel.save()
    _rollen_setzen(verwalter, ziel, rollen_namen)
    adresse_abgleichen(ziel)
    return ziel, passwort


@transaction.atomic
def bearbeiten(verwalter, ziel, rollen_namen: list[str]) -> None:
    """Speichert ein bereits per Formular geändertes Konto und setzt seine Rollen."""
    _pruefen(verwalter, ziel)
    if set(rollen_namen) - set(vergebbare_rollen(verwalter)):
        raise VerwaltungsFehler("Diese Rolle dürfen Sie nicht vergeben.")
    # Ein Superuser bleibt auch ohne die Gruppe Admin; nur ohne Superuser-Recht wäre es eine
    # Herabstufung.
    selbst = ziel.pk == verwalter.pk and not ziel.is_superuser
    if selbst and rollen.ADMIN not in rollen_namen and ist_admin(ziel):
        raise VerwaltungsFehler("Sie können sich die Admin-Rolle nicht selbst nehmen.")
    ziel.save()
    _rollen_setzen(verwalter, ziel, rollen_namen)
    adresse_abgleichen(ziel)


def sperren(verwalter, ziel) -> None:
    _pruefen(verwalter, ziel)
    if ziel.pk == verwalter.pk:
        raise VerwaltungsFehler("Sie können sich nicht selbst sperren.")
    ziel.is_active = False
    ziel.gesperrt_am = timezone.now()
    ziel.gesperrt_von = str(verwalter)[:150]
    ziel.save(update_fields=["is_active", "gesperrt_am", "gesperrt_von"])


def entsperren(verwalter, ziel) -> None:
    _pruefen(verwalter, ziel)
    ziel.is_active = True
    ziel.gesperrt_am = None
    ziel.gesperrt_von = ""
    ziel.save(update_fields=["is_active", "gesperrt_am", "gesperrt_von"])


@transaction.atomic
def werkseinstellungen(verwalter, ziel) -> None:
    """Persönliche Anpassungen zurücksetzen, wie beim Anlegen des Kontos: Spalten der
    Kundenliste, gewählte Ausgabestelle, im Browser gemerkte Ansichten, angefangene Importe.
    Rollen, Rechte, zugeordnete Ausgabestellen, Ausgabetage, Passwort und Zwei-Faktor bleiben."""
    from apps.datenimport.models import ImportSitzung
    from apps.kunden.models import ImportVorbereitung

    _pruefen(verwalter, ziel)
    ziel.kundenliste_aus = []
    ziel.antraege_liste_aus = []
    ziel.listen_spalten_aus = {}
    ziel.gewaehlte_stelle = None
    ziel.ansicht_stand += 1
    ziel.save(update_fields=["kundenliste_aus", "antraege_liste_aus", "listen_spalten_aus",
                             "gewaehlte_stelle", "ansicht_stand"])  # fmt: skip
    ImportSitzung.objects.filter(benutzer=ziel).delete()
    ImportVorbereitung.objects.filter(erstellt_von=ziel).delete()


def passwort_zuruecksetzen(verwalter, ziel) -> str:
    _pruefen(verwalter, ziel)
    passwort = _passwort_neu(ziel)
    ziel.save(update_fields=["password", "passwort_aendern"])
    return passwort
