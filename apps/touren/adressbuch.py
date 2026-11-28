"""Stationen und Adressbuch (ADR 0147, 0184).

Übertragen: Die Station bekommt einen Eintrag im Adressbuch (Organisation) und merkt ihn sich in
``Station.adresse``. Gibt es dort schon eine Organisation mit gleichem Namen und gleicher PLZ,
wird die verknüpft statt einer zweiten angelegt; was auf einer Seite fehlt, wird von der anderen
ergänzt.

Abgleich danach in beide Richtungen: Wird an der Station oder im Adressbuch Name, Ansprechperson,
Anschrift, Telefon oder E-Mail geändert, übernimmt die andere Seite genau die geänderte Angabe
(``vor_speichern()``/``nach_speichern()``, angeschlossen in ``apps.py``). Was nur die Tour
betrifft (Abholtage, Anfahrt, E-Mail für Lieferscheine …), bleibt an der Station.
"""

import re

from django.db import transaction
from django.utils import timezone

from apps.adressen.models import Adresse, AdressKategorie
from apps.touren.models import Station, TourenEinstellungen

# gemeinsame Angaben: Feld der Station → Feld der Adresse („strasse“ = Straße mit Hausnummer)
FELDER = {
    "name": "organisation", "ansprechpartner": "ansprechperson", "strasse": "strasse",
    "plz": "plz", "ort": "ort", "telefon": "telefon", "email": "email",
}  # fmt: skip
VON = "Tourenplanung"  # steht bei „geändert von“, wenn die andere Seite den Anstoß gab
MAERKTE = {Station.Art.MARKT, Station.Art.BAECKEREI, Station.Art.LIEFERANT}
_HAUSNUMMER = re.compile(r"^(.*\D)\s+(\d+\s*[a-zA-Z]?(?:\s*[-/+]\s*\d+\s*[a-zA-Z]?)*)$")


def _wert(objekt, feld: str) -> str:
    if isinstance(objekt, Station) and feld == "strasse":
        return objekt.strasse_hausnummer
    return getattr(objekt, feld) or ""


def _werte(objekt) -> dict:
    felder = FELDER if isinstance(objekt, Station) else FELDER.values()
    return {f: _wert(objekt, f) for f in felder}


def _setzen(objekt, feld: str, wert: str) -> None:
    if isinstance(objekt, Station) and feld == "strasse":
        treffer = _HAUSNUMMER.match(wert.strip())
        strasse, nummer = treffer.groups() if treffer else (wert.strip(), "")
        if len(nummer) > Station._meta.get_field("hausnummer").max_length:
            strasse, nummer = wert.strip(), ""
        objekt.strasse, objekt.hausnummer = strasse.strip(), nummer
        return
    laenge = objekt._meta.get_field(feld).max_length
    setattr(objekt, feld, wert[:laenge] if laenge else wert)


def kategorie_name(station: Station) -> str:
    """In welche Adresskategorie die Station gehört (aus den Einstellungen; leer = keine)."""
    e = TourenEinstellungen.laden()
    if station.art in MAERKTE:
        return e.kategorie_maerkte.strip()
    if station.art == Station.Art.EINRICHTUNG:
        return e.kategorie_einrichtung.strip()
    return ""


def kategorie_setzen(station: Station) -> bool:
    """Gibt der verknüpften Adresse die passende Kategorie (nur hinzufügen, nie wegnehmen).
    Rückgabe: ob sie neu dazukam."""
    name = kategorie_name(station)
    if not name or not station.adresse_id:
        return False
    kategorie = AdressKategorie.objects.filter(name__iexact=name).order_by("pk").first()
    if kategorie is None:
        kategorie = AdressKategorie.objects.create(name=name)
    if not kategorie.aktiv or station.adresse.kategorien.filter(pk=kategorie.pk).exists():
        return False
    station.adresse.kategorien.add(kategorie)
    return True


def vorhandene(station: Station) -> Adresse | None:
    """Organisation im Adressbuch mit gleichem Namen und gleicher PLZ (ohne eigene Station)."""
    return (Adresse.objects.filter(art=Adresse.Art.ORGANISATION,
                                   organisation__iexact=station.name.strip(),
                                   plz=station.plz.strip(), station__isnull=True)
            .order_by("pk").first())  # fmt: skip


def _ergaenzen(station: Station, adresse: Adresse, von: str) -> None:
    """Beim Verknüpfen: Was auf einer Seite leer ist, kommt von der anderen. Wo beide etwas
    anderes haben, bleibt beides stehen, bis jemand die Angabe ändert."""
    an_adresse, an_station = [], []
    for s_feld, a_feld in FELDER.items():
        s_wert, a_wert = _wert(station, s_feld), _wert(adresse, a_feld)
        if s_wert and not a_wert:
            _setzen(adresse, a_feld, s_wert)
            an_adresse.append(a_feld)
        elif a_wert and not s_wert:
            _setzen(station, s_feld, a_wert)
            an_station.append(s_feld)
    jetzt = timezone.now()
    if an_adresse:
        adresse.geaendert_am, adresse.geaendert_von = jetzt, von
        adresse.save()
    if an_station:
        station.geaendert_am, station.geaendert_von = jetzt, von
        station.save()


@transaction.atomic
def uebertragen(station: Station, von: str) -> tuple[Adresse, bool]:
    """Rückgabe: der Eintrag im Adressbuch und ob er neu angelegt wurde."""
    station = Station.objects.select_for_update().get(pk=station.pk)
    if station.adresse_id:
        return station.adresse, False
    adresse = vorhandene(station)
    neu = adresse is None
    if neu:
        email = station.email or station.email_lieferschein
        weitere = station.email_lieferschein if station.email_lieferschein != email else ""
        adresse = Adresse(
            art=Adresse.Art.ORGANISATION, organisation=station.name,
            ansprechperson=station.ansprechpartner, strasse=station.strasse_hausnummer,
            plz=station.plz, ort=station.ort, telefon=station.telefon, email=email,
            email_weitere=weitere, geaendert_am=timezone.now(), geaendert_von=von,
        )  # fmt: skip
        adresse.clean()
        adresse.save()
    station.adresse = adresse
    station.save(update_fields=["adresse"])
    if not neu:
        _ergaenzen(station, adresse, von)
    kategorie_setzen(station)
    return adresse, neu


# --- Abgleich in beide Richtungen ---------------------------------------------------------------


def vor_speichern(sender, instance, raw=False, **kwargs):
    """Merkt sich, wie die gemeinsamen Angaben vor dem Speichern in der Datenbank stehen."""
    instance._abgleich_vorher = None
    if raw or instance.pk is None:
        return
    alt = sender.objects.filter(pk=instance.pk).first()
    if alt is not None:
        instance._abgleich_vorher = _werte(alt)


def _geaendert(instance) -> list[str]:
    vorher = getattr(instance, "_abgleich_vorher", None)
    if vorher is None:
        return []
    jetzt = _werte(instance)
    return [f for f in vorher if vorher[f] != jetzt[f]]


def _uebernehmen(ziel, werte: dict, von: str) -> None:
    """Schreibt die geänderten Angaben ans Ziel, wenn sie dort anders stehen."""
    anders = {f: w for f, w in werte.items() if _wert(ziel, f) != w}
    if not anders:
        return
    for feld, wert in anders.items():
        _setzen(ziel, feld, wert)
    ziel.geaendert_am, ziel.geaendert_von = timezone.now(), von or VON
    ziel.save()


def nach_speichern(sender, instance, raw=False, **kwargs):
    """Station geändert → Adresse; Adresse geändert → Station. Nur die Angaben, die sich bei
    diesem Speichern geändert haben. Ein leerer Name wird nie übernommen; Stationen, die eine
    Ausgabestelle der Tafel sind, ändert das Adressbuch nicht (ADR 0171)."""
    geaendert = _geaendert(instance)
    instance._abgleich_vorher = None
    if raw:
        return
    if sender is Station:
        if not instance.adresse_id:
            return
        kategorie_setzen(instance)  # auch wenn sich die Art der Station geändert hat
        if not geaendert:
            return
        werte = {FELDER[f]: _wert(instance, f) for f in geaendert}
        if not werte.get("organisation", "x"):
            del werte["organisation"]
        _uebernehmen(instance.adresse, werte, instance.geaendert_von)
        return
    station = geaendert and (
        Station.objects.filter(adresse=instance, ausgabestelle__isnull=True).first()
    )
    if not station:
        return
    zurueck = {a: s for s, a in FELDER.items()}
    werte = {zurueck[f]: _wert(instance, f) for f in geaendert}
    if not werte.get("name", "x"):
        del werte["name"]
    _uebernehmen(station, werte, instance.geaendert_von)
