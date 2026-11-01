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
    """Jedes Mitarbeiter-Konto ist eine Person im Adressbuch (ADR 0097): fehlt die verknüpfte
    Adresse, wird sie aus den Kontodaten angelegt. Ob jemand im Dienstplan/Fahrdienst einteilbar
    ist, ergibt sich aus der Rolle. Konten einer Ausgabestelle (Einlass-Tablet) bleiben außen vor;
    sie sind keine Person."""
    from apps.adressen.models import Adresse

    if ziel.stelle_id or Adresse.objects.filter(konto=ziel).exists():
        return
    stamm = getattr(ziel, "stammdaten", None)
    Adresse.objects.create(
        art=Adresse.Art.PERSON, konto=ziel,
        vorname=(ziel.first_name or "")[:100],
        nachname=(ziel.last_name or ziel.get_username())[:100],
        email=ziel.email or "",
        anrede=getattr(stamm, "anrede", "") or "",
        strasse=getattr(stamm, "strasse", "") or "",
        plz=getattr(stamm, "plz", "") or "",
        ort=getattr(stamm, "ort", "") or "",
        telefon=getattr(stamm, "telefon", "") or "",
        mobil=getattr(stamm, "handy", "") or "",
    )  # fmt: skip


# Kategorien, die eine Mitarbeit im Adressbuch sichtbar machen (ADR 0098). Beide werden immer nur
# ergänzt, nie automatisch entfernt: So bleibt jemand auch nach dem Ausscheiden als (ehemaliger)
# Helfer auffindbar, z. B. für einen Serienbrief.
HELFER_KATEGORIE = "Ehrenamtliche Helfer"
EHEMALIGE_KATEGORIE = "Ehemalige Ehrenamtliche"


def _kategorie_ergaenzen(ziel, name) -> None:
    """Hängt dem Adressbuch-Eintrag des Kontos die genannte Kategorie additiv an. Konten einer
    Ausgabestelle (Einlass-Tablet) sind keine Person und bleiben außen vor."""
    from apps.adressen.models import Adresse, AdressKategorie

    if ziel.stelle_id:
        return
    adresse = Adresse.objects.filter(konto=ziel).first()
    if adresse is None:
        return
    kategorie, _ = AdressKategorie.objects.get_or_create(name=name)
    adresse.kategorien.add(kategorie)


def helfer_kennzeichnen(ziel) -> None:
    """Wer ein Konto mit mindestens einer Rolle hat, gilt als ehrenamtlicher Helfer (ADR 0098):
    die Kategorie „Ehrenamtliche Helfer“ wird additiv gesetzt und bleibt erhalten, auch wenn
    später eine Rolle wegfällt."""
    if ziel.groups.exists():
        _kategorie_ergaenzen(ziel, HELFER_KATEGORIE)


def _pruefen(verwalter, ziel):
    if not darf_bearbeiten(verwalter, ziel):
        raise VerwaltungsFehler("Admin-Konten kann nur ein Admin bearbeiten.")


def rollen_setzen(verwalter, konto, rollen_namen) -> None:
    """Öffentliche Fassung für die Adress-Maske (ADR 0097): prüft wie beim Bearbeiten und setzt
    die vergebbaren Rollen; nicht vergebbare Rollen bleiben."""
    _pruefen(verwalter, konto)
    if set(rollen_namen) - set(vergebbare_rollen(verwalter)):
        raise VerwaltungsFehler("Diese Rolle dürfen Sie nicht vergeben.")
    _rollen_setzen(verwalter, konto, rollen_namen)
    helfer_kennzeichnen(konto)


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
    helfer_kennzeichnen(ziel)
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
    helfer_kennzeichnen(ziel)


def sperren(verwalter, ziel) -> None:
    _pruefen(verwalter, ziel)
    if ziel.pk == verwalter.pk:
        raise VerwaltungsFehler("Sie können sich nicht selbst sperren.")
    ziel.is_active = False
    ziel.gesperrt_am = timezone.now()
    ziel.gesperrt_von = str(verwalter)[:150]
    ziel.save(update_fields=["is_active", "gesperrt_am", "gesperrt_von"])
    # Ausgeschiedene Mitarbeitende zusätzlich als „Ehemalige“ führen (ADR 0098); die Kategorie
    # „Ehrenamtliche Helfer“ bleibt dabei erhalten.
    _kategorie_ergaenzen(ziel, EHEMALIGE_KATEGORIE)


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
