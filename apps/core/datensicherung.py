"""Datenexport und Zurücklesen in der Oberfläche (ADR 0037).

Ergänzt die tägliche Server-Sicherung (Dienst ``backup``): Ein Admin lädt alle Daten oder einzelne
Bereiche als eine Datei herunter, verschlüsselt mit einem selbst gewählten Passwort, und kann sie
später zurücklesen. Eine Teildatei (oder der Modus „aktualisieren“) fügt hinzu und überschreibt
gleiche Datensätze, löscht aber nie. „Vollständig ersetzen“ gibt es nur für eine vollständige
Exportdatei.

Dateiformat: Kopfzeile ``BINTAFELN-EXPORT-1``, 16 Byte Salz, danach ein Fernet-Token (Schlüssel per
PBKDF2-SHA256 aus dem Passwort) über gzip-komprimiertes JSON.
"""

import base64
import gzip
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from auditlog.context import disable_auditlog
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management.color import no_style
from django.db import IntegrityError, connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.core import geheimnis, module

KOPF = b"BINTAFELN-EXPORT-1\n"
FORMAT, VERSION = "bintafeln-datenexport", 1
ITERATIONEN = 480_000
MIN_PASSWORT = 10
EIGENE_APPS = [
    "core",
    "konten",
    "kunden",
    "ausgabe",
    "personal",
    "antraege",
    "adressen",
    "spenden",
    "mitglieder",
    "serienbriefe",
    "datenimport",
]
# Vorübergehende Daten, die nicht in einen Export gehören
AUSGENOMMEN = {"kunden.importvorbereitung", "antraege.antragversuch", "core.sicherungsdienst",
               "konten.vertrautesgeraet", "datenimport.importsitzung", "core.meldung"}  # fmt: skip
EINSTELLUNGS_MODELLE = {
    "core.tafeleinstellungen", "core.maileinstellungen", "core.fotoeinstellungen",
    "kunden.kundeneinstellungen",
    "kunden.zusatzfeld", "kunden.ausgabestelle", "kunden.kundengruppe", "kunden.einkommensart",
    "kunden.notizvorlage", "kunden.dokumentart", "kunden.ausweisvorlage",
    "ausgabe.ausgabeeinstellungen", "ausgabe.beitragsfreierzeitraum", "ausgabe.sonderausgabe",
    "antraege.antrageinstellungen", "antraege.antragtext", "personal.arbeitszeiteinstellungen",
    "konten.personaleinstellungen", "konten.dokumentkategorie", "adressen.adresskategorie",
    "spenden.spendeneinstellungen", "mitglieder.mitgliedereinstellungen",
    "konten.anmeldeeinstellungen",
}  # fmt: skip
BEREICHE = {
    "einstellungen": "Einstellungen und Listen (Tafel, Kundengruppen, Ausgabestellen, …)",
    "kunden": "Kunden und Ausgabe (Haushalte, Abholungen, Kundenkonto, Notizen, Sonderaktionen)",
    "antraege": "Anträge",
    "adressen": "Adressbuch, Spenden und Mitglieder",
    "mitarbeitende": "Konten, Rollen und Angestellten-Daten",
    "protokoll": "Änderungsprotokoll",
    "dateien": "Hochgeladene Dateien (Dokumente, Logo, Anhänge)",
}
APP_BEREICH = {
    "kunden": "kunden",
    "ausgabe": "kunden",
    "antraege": "antraege",
    "konten": "mitarbeitende",
    "personal": "mitarbeitende",
    "core": "einstellungen",
    "adressen": "adressen",
    "spenden": "adressen",
    "mitglieder": "adressen",
    "serienbriefe": "adressen",
    "datenimport": "einstellungen",
}
# Zuschaltbare Module (ADR 0049) bringen Bereich und Ausnahmen selbst mit
for _m in module.alle():
    EIGENE_APPS.append(_m.app_label)
    APP_BEREICH[_m.app_label] = _m.sicherung_bereich
    AUSGENOMMEN.update(_m.sicherung_ausgenommen)


class DatensicherungsFehler(ValueError):
    pass


def _label(modell) -> str:
    return modell._meta.label_lower


def modelle(bereich: str) -> list:
    """Modelle eines Bereichs in einer Reihenfolge, in der Fremdschlüssel vorher dastehen."""
    if bereich == "protokoll":
        return [apps.get_model("auditlog", "LogEntry")]
    if bereich == "dateien":
        return []
    ergebnis = []
    if bereich == "mitarbeitende":
        ergebnis.append(apps.get_model("auth", "Group"))
    for app in EIGENE_APPS:
        for m in apps.get_app_config(app).get_models():
            label = _label(m)
            if label in AUSGENOMMEN:
                continue
            ziel = "einstellungen" if label in EINSTELLUNGS_MODELLE else APP_BEREICH[app]
            if ziel == bereich:
                ergebnis.append(m)
    return ergebnis


def _schluessel(passwort: str, salz: bytes) -> Fernet:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salz, iterations=ITERATIONEN)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(passwort.encode())))


def _migrationsstand() -> dict[str, str]:
    stand = {}
    for eintrag in MigrationRecorder.Migration.objects.filter(app__in=EIGENE_APPS):
        if eintrag.name > stand.get(eintrag.app, ""):
            stand[eintrag.app] = eintrag.name
    return stand


def _dateien() -> dict[str, str]:
    """Alle hochgeladenen Dateien als Base64; verschlüsselt abgelegte werden entschlüsselt."""
    wurzel = Path(settings.MEDIA_ROOT)
    ergebnis = {}
    if not wurzel.is_dir():
        return ergebnis
    for pfad in sorted(p for p in wurzel.rglob("*") if p.is_file()):
        relativ = pfad.relative_to(wurzel).as_posix()
        inhalt = pfad.read_bytes()
        if relativ.startswith("privat/"):
            klar = geheimnis.bytes_entschluesseln(inhalt)
            if klar is None:  # mit fremdem Schlüssel: nicht lesbar, deshalb nicht exportieren
                continue
            inhalt = klar
        ergebnis[relativ] = base64.b64encode(inhalt).decode()
    return ergebnis


def exportieren(bereiche: list[str], passwort: str, von: str = "") -> bytes:
    """Erzeugt die verschlüsselte Exportdatei."""
    from apps.core.models import TafelEinstellungen
    from bintafeln.version import version

    bereiche = [b for b in BEREICHE if b in bereiche]
    if not bereiche:
        raise DatensicherungsFehler("Bitte mindestens einen Bereich wählen.")
    if len(passwort) < MIN_PASSWORT:
        raise DatensicherungsFehler(f"Das Passwort braucht mindestens {MIN_PASSWORT} Zeichen.")
    objekte = []
    for bereich in bereiche:
        for m in modelle(bereich):
            objekte.extend(m._default_manager.order_by("pk"))
    tafel = TafelEinstellungen.laden()
    inhalt = {
        "format": FORMAT, "version": VERSION, "erstellt": timezone.now().isoformat(),
        "erstellt_von": von, "bintafeln": version(), "tafel": tafel.name,
        "installation": str(tafel.installation), "bereiche": bereiche,
        "vollstaendig": set(bereiche) == set(BEREICHE), "migrationen": _migrationsstand(),
        "daten": json.loads(serializers.serialize("json", objekte)),
        "dateien": _dateien() if "dateien" in bereiche else {},
    }  # fmt: skip
    salz = os.urandom(16)
    roh = gzip.compress(json.dumps(inhalt, ensure_ascii=False).encode())
    return KOPF + salz + _schluessel(passwort, salz).encrypt(roh)


def lesen(datei: bytes, passwort: str) -> dict:
    """Entschlüsselt und prüft eine Exportdatei; Fehler verständlich als DatensicherungsFehler."""
    if not datei.startswith(KOPF) or len(datei) < len(KOPF) + 17:
        raise DatensicherungsFehler("Das ist keine Exportdatei von bintafeln.")
    salz = datei[len(KOPF) : len(KOPF) + 16]
    try:
        roh = _schluessel(passwort, salz).decrypt(datei[len(KOPF) + 16 :])
        inhalt = json.loads(gzip.decompress(roh))
    except InvalidToken:
        raise DatensicherungsFehler("Das Passwort passt nicht zu dieser Datei.") from None
    except (OSError, ValueError):
        raise DatensicherungsFehler("Die Datei ist beschädigt.") from None
    if inhalt.get("format") != FORMAT or not isinstance(inhalt.get("daten"), list):
        raise DatensicherungsFehler("Das ist keine Exportdatei von bintafeln.")
    if inhalt.get("version", 0) > VERSION:
        raise DatensicherungsFehler("Die Datei stammt aus einer neueren bintafeln-Version.")
    hier = _migrationsstand()
    for app, name in (inhalt.get("migrationen") or {}).items():
        if app in hier and name > hier[app]:
            raise DatensicherungsFehler(
                "Die Datei stammt aus einer neueren bintafeln-Version (Datenbankstand "
                f"{app} {name}). Bitte zuerst bintafeln aktualisieren."
            )
    return inhalt


@dataclass
class Vorschau:
    tafel: str
    erstellt: str
    erstellt_von: str
    bintafeln: str
    vollstaendig: bool
    andere_installation: bool
    bereiche: list[str]
    zeilen: list[dict] = field(default_factory=list)  # Modell, neu, vorhanden
    dateien: int = 0


def vorschau(inhalt: dict) -> Vorschau:
    from apps.core.models import TafelEinstellungen

    je_modell: dict[str, list] = {}
    for eintrag in inhalt["daten"]:
        je_modell.setdefault(eintrag["model"], []).append(eintrag.get("pk"))
    zeilen = []
    for label, pks in je_modell.items():
        try:
            m = apps.get_model(label)
        except LookupError:
            zeilen.append({"name": label, "neu": 0, "vorhanden": 0, "unbekannt": len(pks)})
            continue
        vorhanden = m._default_manager.filter(pk__in=pks).count()
        zeilen.append({"name": str(m._meta.verbose_name_plural), "neu": len(pks) - vorhanden,
                       "vorhanden": vorhanden, "unbekannt": 0})  # fmt: skip
    return Vorschau(
        tafel=inhalt.get("tafel", ""), erstellt=inhalt.get("erstellt", ""),
        erstellt_von=inhalt.get("erstellt_von", ""), bintafeln=inhalt.get("bintafeln", ""),
        vollstaendig=bool(inhalt.get("vollstaendig")),
        andere_installation=inhalt.get("installation")
        != str(TafelEinstellungen.laden().installation),
        bereiche=[BEREICHE.get(b, b) for b in inhalt.get("bereiche", [])], zeilen=zeilen,
        dateien=len(inhalt.get("dateien") or {}),
    )  # fmt: skip


def _dateien_schreiben(dateien: dict[str, str]) -> int:
    wurzel = Path(settings.MEDIA_ROOT).resolve()
    anzahl = 0
    for relativ, b64 in dateien.items():
        ziel = (wurzel / relativ).resolve()
        if wurzel not in ziel.parents:  # keine Pfade außerhalb von MEDIA_ROOT
            continue
        inhalt = base64.b64decode(b64)
        if relativ.startswith("privat/"):
            inhalt = geheimnis.bytes_verschluesseln(inhalt)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
        anzahl += 1
    return anzahl


def zuruecklesen(inhalt: dict, ersetzen: bool = False) -> Counter:
    """Spielt die Daten ein. Ohne ``ersetzen`` wird nur hinzugefügt bzw. aktualisiert."""
    if ersetzen and not inhalt.get("vollstaendig"):
        raise DatensicherungsFehler("Ersetzen geht nur mit einer vollständigen Exportdatei.")
    try:
        gezaehlt = _einspielen(inhalt, ersetzen)
    except IntegrityError:
        raise DatensicherungsFehler(
            "Die Datei verweist auf Daten, die hier fehlen (z. B. Kundengruppen oder Konten). "
            "Bitte die zugehörigen Bereiche mit einlesen, etwa „Einstellungen und Listen“. "
            "Es wurde nichts verändert."
        ) from None
    if inhalt.get("dateien"):
        gezaehlt["Dateien"] = _dateien_schreiben(inhalt["dateien"])
    return gezaehlt


def _einspielen(inhalt: dict, ersetzen: bool) -> Counter:
    gezaehlt = Counter()
    betroffen = set()
    with transaction.atomic(), disable_auditlog():
        if ersetzen:
            for bereich in reversed(list(BEREICHE)):
                for m in reversed(modelle(bereich)):
                    m._default_manager.all().delete()
        for obj in serializers.deserialize("json", json.dumps(inhalt["daten"]),
                                           ignorenonexistent=True):  # fmt: skip
            obj.save()
            betroffen.add(type(obj.object))
            gezaehlt[str(type(obj.object)._meta.verbose_name_plural)] += 1
        # Fortlaufende Nummern der Datenbank hinter die eingelesenen Schlüssel setzen
        befehle = connection.ops.sequence_reset_sql(no_style(), list(betroffen))
        with connection.cursor() as cursor:
            for befehl in befehle:
                cursor.execute(befehl)
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # Verweise jetzt prüfen
    return gezaehlt
