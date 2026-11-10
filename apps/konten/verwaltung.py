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


# Adressfelder, die Mitarbeiter-Stammdaten (links) und der Adressbuch-Eintrag (rechts) beide
# führen. Damit nicht zwei Stände derselben Adresse auseinanderlaufen, zieht beim Speichern der
# einen Seite die andere mit (ADR 0097): die Mitarbeiterseite schreibt ins Adressbuch, das
# Adressbuch zurück in die Stammdaten.
ADRESS_FELDER = [
    ("anrede", "anrede"), ("strasse", "strasse"), ("plz", "plz"),
    ("ort", "ort"), ("telefon", "telefon"), ("handy", "mobil"),
]  # fmt: skip


def adresse_aus_stammdaten(konto, *, von: str = "") -> None:
    """Nach dem Speichern der Mitarbeiter-Stammdaten den verknüpften Adressbuch-Eintrag mitziehen.
    Konten einer Ausgabestelle sind keine Person und bleiben außen vor."""
    from apps.adressen.models import Adresse

    if konto.stelle_id:
        return
    stamm = getattr(konto, "stammdaten", None)
    adresse = Adresse.objects.filter(konto=konto).first()
    if stamm is None or adresse is None:
        return
    aenderung = {a: (getattr(stamm, s, "") or "") for s, a in ADRESS_FELDER
                 if getattr(adresse, a) != (getattr(stamm, s, "") or "")}  # fmt: skip
    if aenderung:
        for feld, wert in aenderung.items():
            setattr(adresse, feld, wert)
        adresse.geaendert_am = timezone.now()
        if von:
            adresse.geaendert_von = von
        adresse.save(update_fields=[*aenderung, "geaendert_am", "geaendert_von"])


def stammdaten_aus_adresse(adresse) -> None:
    """Nach dem Speichern eines Adressbuch-Eintrags die Mitarbeiter-Stammdaten des verknüpften
    Kontos mitziehen (umgekehrte Richtung)."""
    from apps.konten.models import Stammdaten

    konto = adresse.konto
    if konto is None or konto.stelle_id:
        return
    stamm, _ = Stammdaten.objects.get_or_create(benutzer=konto)
    aenderung = {s: (getattr(adresse, a, "") or "") for s, a in ADRESS_FELDER
                 if getattr(stamm, s) != (getattr(adresse, a, "") or "")}  # fmt: skip
    if aenderung:
        for feld, wert in aenderung.items():
            setattr(stamm, feld, wert)
        stamm.save(update_fields=list(aenderung))


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


@transaction.atomic
def sammel_rolle(verwalter, konten, rolle_name: str, *, entfernen: bool) -> int:
    """Fügt mehreren Konten auf einmal eine einzelne Rolle hinzu oder nimmt sie ihnen; die übrigen
    Rollen bleiben. Liefert die Zahl der tatsächlich geänderten Konten. Unangetastet bleiben Konten,
    die der Verwalter nicht bearbeiten darf (Admin-Konten), und – beim Entfernen – das eigene Konto,
    wenn es die Admin-Rolle beträfe (niemand nimmt sich selbst die Admin-Rolle)."""
    from django.contrib.auth.models import Group

    if rolle_name not in vergebbare_rollen(verwalter):
        raise VerwaltungsFehler("Diese Rolle dürfen Sie nicht vergeben.")
    gruppe = Group.objects.get(name=rolle_name)
    geaendert = 0
    for konto in konten:
        if not darf_bearbeiten(verwalter, konto):
            continue
        selbst = konto.pk == verwalter.pk and not konto.is_superuser
        if entfernen and selbst and rolle_name == rollen.ADMIN:
            continue
        hat = konto.groups.filter(pk=gruppe.pk).exists()
        if entfernen and hat:
            konto.groups.remove(gruppe)
        elif not entfernen and not hat:
            konto.groups.add(gruppe)
        else:
            continue  # nichts zu tun (schon vorhanden bzw. schon weg)
        rollen.rechte_vergessen(konto)
        if not entfernen:
            helfer_kennzeichnen(konto)
        geaendert += 1
    return geaendert


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
    personalnummer_zuweisen(ziel)
    return ziel, passwort


def _freier_benutzername(adresse) -> str:
    """Ein noch freier Benutzername aus dem Namen der Adresse (z. B. „rene.wiechert"); bei
    Dopplung mit angehängter Zahl. Leerer Name → „helfer"."""
    from django.utils.text import slugify

    teile = [slugify(adresse.vorname or ""), slugify(adresse.nachname or "")]
    basis = ".".join(t for t in teile if t) or "helfer"
    basis = basis[:140]
    Benutzer = get_user_model()
    name, n = basis, 1
    while Benutzer.objects.filter(username__iexact=name).exists():
        n += 1
        name = f"{basis}{n}"
    return name


@transaction.atomic
def konto_fuer_adresse(verwalter, adresse, rollen_namen: list[str]):
    """Legt für eine Adressbuch-Person ohne Konto ein Anmelde-Konto an und setzt die Rollen darauf
    (ADR 0097). Ohne nutzbares Passwort und ohne Mail – die Person kann später eingeladen werden.
    Nötig, weil Rollen am Konto hängen: ohne Konto hätte eine Rolle keinen Platz."""
    if set(rollen_namen) - set(vergebbare_rollen(verwalter)):
        raise VerwaltungsFehler("Diese Rolle dürfen Sie nicht vergeben.")
    ziel = get_user_model()(
        username=_freier_benutzername(adresse),
        first_name=(adresse.vorname or "")[:150],
        last_name=(adresse.nachname or "")[:150],
        email=adresse.email or "",
        beschaeftigung="ehrenamtlich",
    )
    ziel.set_unusable_password()
    ziel.save()
    adresse.konto = ziel
    adresse.save(update_fields=["konto"])
    _rollen_setzen(verwalter, ziel, rollen_namen)
    helfer_kennzeichnen(ziel)
    personalnummer_zuweisen(ziel)
    return ziel


def naechste_personalnummer() -> int:
    """Nächste freie Personalnummer aus dem eigenen Mitarbeiter-Nummernkreis (Zeile gesperrt,
    damit nie doppelt). Unabhängig von den Mitgliedsnummern (ADR 0116)."""
    from apps.konten.models import PersonalEinstellungen, Stammdaten

    with transaction.atomic():
        e = PersonalEinstellungen.laden()
        e = PersonalEinstellungen.objects.select_for_update().get(pk=e.pk)
        nummer = e.naechste_personalnummer or 1
        while Stammdaten.objects.filter(personalnummer=nummer).exists():
            nummer += 1
        e.naechste_personalnummer = nummer + 1
        e.save(update_fields=["naechste_personalnummer"])
        return nummer


def personalnummer_verbraucht(nummer: int) -> None:
    """Nach einer von Hand gesetzten Personalnummer den Zähler dahinter rücken."""
    from apps.konten.models import PersonalEinstellungen

    PersonalEinstellungen.laden()
    PersonalEinstellungen.objects.filter(naechste_personalnummer__lte=nummer).update(
        naechste_personalnummer=nummer + 1
    )


def personalnummer_zuweisen(konto) -> None:
    """Gibt dem Konto eine Personalnummer aus dem eigenen Mitarbeiter-Nummernkreis (ADR 0116),
    sofern es noch keine hat. Mitglied oder nicht spielt keine Rolle – die Personalnummer ist
    unabhängig von der Mitgliedsnummer."""
    from apps.konten.models import Stammdaten

    sd, _ = Stammdaten.objects.get_or_create(benutzer=konto)
    if sd.personalnummer is not None:
        return
    sd.personalnummer = naechste_personalnummer()
    sd.save(update_fields=["personalnummer"])


def personennummer(konto) -> str:
    """Die Personalnummer des Mitarbeitenden für die Mitarbeitendenliste (oder leer). Eigener
    Nummernkreis, unabhängig von einer etwaigen Mitgliedsnummer der Person (ADR 0116)."""
    nummer = getattr(getattr(konto, "stammdaten", None), "personalnummer", None)
    return str(nummer) if nummer else ""


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


def zugang_sperren(verwalter, ziel) -> None:
    """Nur den Online-Zugang sperren (ADR 0114): Die Person kann sich nicht mehr anmelden, bleibt
    aber aktiver Helfer (nicht im Archiv); Rollen, Rechte und Passwort bleiben. Anders als
    ``sperren`` wird das Konto nicht archiviert."""
    _pruefen(verwalter, ziel)
    if ziel.pk == verwalter.pk:
        raise VerwaltungsFehler("Sie können sich den eigenen Online-Zugang nicht sperren.")
    ziel.zugang_gesperrt = True
    ziel.save(update_fields=["zugang_gesperrt"])


def zugang_entsperren(verwalter, ziel) -> None:
    """Den zuvor gesperrten Online-Zugang wieder freigeben; das bisherige Passwort gilt sofort
    wieder (kein neues Startpasswort nötig)."""
    _pruefen(verwalter, ziel)
    ziel.zugang_gesperrt = False
    ziel.save(update_fields=["zugang_gesperrt"])


def anmeldesperre_aufheben(verwalter, ziel) -> None:
    """Die vorübergehende Sperre nach zu vielen falschen Passwörtern sofort aufheben (ADR 0120);
    das Passwort bleibt, wie es ist."""
    from apps.konten import anmeldesperre

    _pruefen(verwalter, ziel)
    anmeldesperre.aufheben(ziel.get_username())


def entfernen(verwalter, ziel):
    """Löscht ein gesperrtes (archiviertes) Mitarbeiter-Konto samt Stammdaten und verknüpfter
    Adresse in den Papierkorb (Ausnahme zu ADR 0015). Alles, was am Konto hängt (Verträge,
    Stunden, Urlaub, Abwesenheiten, Zeitbuchungen, PIN, Import-Vorlagen), kommt als Teil der
    Löschung mit; wo die Person nur als „eingetragen/gesehen von“ an fremden Vorgängen steht,
    wird sie dort auf leer gesetzt (und bei einer Wiederherstellung zurückgesetzt).

    Nur gesperrte Konten, nie das eigene; Admin-Konten nur durch einen Admin. Hat die Person
    Spenden oder eine Mitgliedschaft, löst das Löschen ``ProtectedError`` aus und es wird nichts
    gelöscht (wie im Adressbuch). Gibt den ``PapierkorbEintrag`` zurück."""
    from apps.adressen.models import Adresse
    from apps.core import papierkorb

    _pruefen(verwalter, ziel)
    if ziel.pk == verwalter.pk:
        raise VerwaltungsFehler("Sie können sich nicht selbst löschen.")
    if ziel.is_active:
        raise VerwaltungsFehler("Nur gesperrte (archivierte) Konten lassen sich löschen; "
                                "bitte das Konto zuerst sperren.")  # fmt: skip
    adresse = Adresse.objects.filter(konto=ziel).first()
    objekte = [ziel] + ([adresse] if adresse else [])
    return papierkorb.loeschen(verwalter, "Mitarbeiter", str(ziel), *objekte,
                               recht="mitarbeitende.loeschen")  # fmt: skip


def konto_und_adresse_entfernen(verwalter, adresse):
    """Löscht eine Adressbuch-Person samt ihrem Anmelde-Konto in den Papierkorb – Adresse und Konto
    gehören zusammen (ADR 0097), eine ohne die andere wäre ein verwaister Zugang. Anders als beim
    Mitarbeiter-Löschen geht das auch bei einem noch aktiven Konto, weil hier die ganze Person
    entfernt wird. Prüft die Rechte und Schutzregeln; ``ProtectedError`` (Spenden/Mitgliedschaft)
    lässt nichts löschen. Gibt den ``PapierkorbEintrag`` zurück."""
    from apps.core import papierkorb

    ziel = adresse.konto
    _pruefen(verwalter, ziel)  # Admin-Konten nur durch einen Admin
    if ziel.pk == verwalter.pk:
        raise VerwaltungsFehler("Sie können sich nicht selbst löschen.")
    if not rollen.hat_recht(verwalter, "mitarbeitende.loeschen"):
        raise VerwaltungsFehler("Diese Person hat ein Mitarbeiter-Konto; zum Löschen brauchen Sie "
                                "auch das Recht, Mitarbeitende zu löschen.")  # fmt: skip
    return papierkorb.loeschen(verwalter, "Mitarbeiter", str(ziel), ziel, adresse,
                               recht="mitarbeitende.loeschen")  # fmt: skip


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
    ziel.warteliste_ansicht = {}
    ziel.liste_zeilen = ""
    ziel.gewaehlte_stelle = None
    ziel.ansicht_stand += 1
    ziel.save(update_fields=["kundenliste_aus", "antraege_liste_aus", "listen_spalten_aus",
                             "warteliste_ansicht", "liste_zeilen", "gewaehlte_stelle",
                             "ansicht_stand"])  # fmt: skip
    ImportSitzung.objects.filter(benutzer=ziel).delete()
    ImportVorbereitung.objects.filter(erstellt_von=ziel).delete()


def passwort_zuruecksetzen(verwalter, ziel) -> str:
    _pruefen(verwalter, ziel)
    passwort = _passwort_neu(ziel)
    ziel.save(update_fields=["password", "passwort_aendern"])
    return passwort


def startpasswort_basis(ziel) -> tuple[str, str]:
    """Das Startpasswort beim Freigeben und seine Herkunft: zuerst das **Geburtsdatum** mit Punkten
    (z. B. „15.03.1980“), sonst **Straße und Hausnummer** (wie hinterlegt) – beides kennt die Person
    selbst. Liefert (passwort, basis) mit basis ∈ {"geburtsdatum", "adresse"}; fehlt beides, wird
    ``VerwaltungsFehler`` geworfen."""
    sd = getattr(ziel, "stammdaten", None)
    geburtsdatum = getattr(sd, "geburtsdatum", None)
    if geburtsdatum:
        return geburtsdatum.strftime("%d.%m.%Y"), "geburtsdatum"
    strasse = (getattr(sd, "strasse", "") or "").strip()
    if strasse:
        return strasse, "adresse"
    raise VerwaltungsFehler(
        "Weder Geburtsdatum noch Straße hinterlegt – bitte erst nachtragen "
        "oder stattdessen einen Link zum Festlegen des Passworts schicken."
    )


def freigeben(verwalter, ziel) -> str:
    """Gibt den Online-Zugang eines Kontos frei (ADR 0114): Startpasswort aus dem Geburtsdatum
    (sonst der Adresse), Pflicht zum Passwortwechsel bei der ersten Anmeldung, Konto aktiv. Liefert
    die Basis des Startpassworts ("geburtsdatum"/"adresse") für die passende E-Mail."""
    _pruefen(verwalter, ziel)
    passwort, basis = startpasswort_basis(ziel)
    ziel.set_password(passwort)
    ziel.passwort_aendern = True
    ziel.is_active = True
    ziel.gesperrt_am = None
    ziel.gesperrt_von = ""
    ziel.zugang_gesperrt = False
    ziel.save(update_fields=["password", "passwort_aendern", "is_active",
                             "gesperrt_am", "gesperrt_von", "zugang_gesperrt"])  # fmt: skip
    return basis
