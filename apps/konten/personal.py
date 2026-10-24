"""Wiedervorlagen (Führerschein, IfSG-Belehrung) und Löschfrist der Stammdaten (ADR 0017)."""

import calendar
import datetime as dt
import uuid
from dataclasses import dataclass
from pathlib import Path

from auditlog.context import disable_auditlog
from auditlog.models import LogEntry
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core import geheimnis
from apps.konten import rollen
from apps.konten.models import PersonalEinstellungen, Schulung, Stammdaten

KOPIE_TYPEN = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
KOPIE_MAX = 5 * 1024 * 1024

# Wer mit Lebensmitteln umgeht und deshalb die Belehrung nach § 43 IfSG braucht.
IFSG_ROLLEN = (rollen.AUSGABE, rollen.FAHRER, rollen.BEIFAHRER)

# Felder, die die Löschfrist leert. Name, Rollen, Eintritt und Austritt bleiben im Archiv.
PERSOENLICHE_FELDER = [
    "anrede", "strasse", "plz", "ort", "telefon", "handy", "notfall_name", "notfall_telefon",
    "bemerkung", "fs_klassen", "fs_gesehen_von",
]  # fmt: skip
PERSOENLICHE_DATEN = [
    "geburtsdatum", "fs_gueltig_bis", "fs_gesehen_am", "ifsg_erstbelehrung_am",
    "ifsg_belehrung_am",
]  # fmt: skip


def monate_spaeter(datum: dt.date, monate: int) -> dt.date:
    index = datum.year * 12 + datum.month - 1 + monate
    jahr, monat = index // 12, index % 12 + 1
    return datum.replace(
        year=jahr, month=monat, day=min(datum.day, calendar.monthrange(jahr, monat)[1])
    )


@dataclass
class Faelligkeit:
    benutzer: object
    was: str
    faellig_am: dt.date | None  # None = noch nie eingetragen

    @property
    def ueberfaellig(self) -> bool:
        return self.faellig_am is None or self.faellig_am < timezone.localdate()


def _stammdaten(benutzer):
    try:
        return benutzer.stammdaten
    except Stammdaten.DoesNotExist:
        return Stammdaten(benutzer=benutzer)


def faelligkeiten(heute: dt.date | None = None) -> list[Faelligkeit]:
    """Alles, was bei aktiven Mitarbeitenden fällig ist oder innerhalb des Vorlaufs fällig wird."""
    heute = heute or timezone.localdate()
    e = PersonalEinstellungen.laden()
    grenze = heute + dt.timedelta(days=e.vorlauf_tage)
    ergebnis = []
    aktive = (
        get_user_model()
        .objects.filter(is_active=True)
        .select_related("stammdaten")
        .prefetch_related("groups", "schulungen")
        .order_by("last_name", "first_name", "username")
    )
    for b in aktive:
        s = _stammdaten(b)
        namen = {g.name for g in b.groups.all()}
        if rollen.FAHRER in namen:
            if s.fs_gueltig_bis and s.fs_gueltig_bis <= grenze:
                ergebnis.append(Faelligkeit(b, "Führerschein läuft ab", s.fs_gueltig_bis))
            naechste = (
                monate_spaeter(s.fs_gesehen_am, e.fs_pruefung_monate) if s.fs_gesehen_am else None
            )
            if naechste is None or naechste <= grenze:
                ergebnis.append(Faelligkeit(b, "Führerschein ansehen", naechste))
        if namen & set(IFSG_ROLLEN):
            letzte = s.letzte_ifsg_belehrung
            naechste = monate_spaeter(letzte, e.ifsg_wiederholung_monate) if letzte else None
            if naechste is None or naechste <= grenze:
                ergebnis.append(Faelligkeit(b, "Belehrung nach IfSG", naechste))
        # Je Thema zählt die jüngste Schulung; eine Auffrischung erledigt die alte.
        juengste = {}
        for sch in sorted(b.schulungen.all(), key=lambda x: x.datum):
            juengste[sch.thema.strip().lower()] = sch
        for sch in juengste.values():
            if sch.gueltig_bis and sch.gueltig_bis <= grenze:
                ergebnis.append(Faelligkeit(b, f"Schulung „{sch.thema}“", sch.gueltig_bis))
    return ergebnis


# --- Führerschein-Kopie -----------------------------------------------------------------


class KopieFehler(ValueError):
    pass


def _kopie_pfad(name: str) -> Path:
    return Path(settings.MEDIA_ROOT) / "privat" / "fuehrerschein" / name


def kopie_speichern(stammdaten: Stammdaten, datei) -> None:
    """Speichert eine hochgeladene Kopie verschlüsselt und ersetzt eine vorhandene."""
    if not PersonalEinstellungen.laden().fs_kopie_erlaubt:
        raise KopieFehler("Kopien sind in den Einstellungen nicht erlaubt.")
    if datei.content_type not in KOPIE_TYPEN:
        raise KopieFehler("Bitte ein Foto (JPG, PNG, WebP) oder ein PDF hochladen.")
    if datei.size > KOPIE_MAX:
        raise KopieFehler("Die Datei darf höchstens 5 MB groß sein.")
    name = f"{uuid.uuid4().hex}.bin"
    pfad = _kopie_pfad(name)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(geheimnis.bytes_verschluesseln(datei.read()))
    kopie_loeschen(stammdaten, speichern=False)
    stammdaten.fs_kopie_datei, stammdaten.fs_kopie_typ = name, datei.content_type
    stammdaten.fs_kopie_am = timezone.now()
    stammdaten.save()


def kopie_lesen(stammdaten: Stammdaten) -> bytes | None:
    """Entschlüsselte Kopie oder None, wenn keine da oder nicht mehr lesbar ist."""
    if not stammdaten.fs_kopie_datei:
        return None
    pfad = _kopie_pfad(stammdaten.fs_kopie_datei)
    return geheimnis.bytes_entschluesseln(pfad.read_bytes()) if pfad.exists() else None


def kopie_loeschen(stammdaten: Stammdaten, speichern=True) -> None:
    if stammdaten.fs_kopie_datei:
        _kopie_pfad(stammdaten.fs_kopie_datei).unlink(missing_ok=True)
    stammdaten.fs_kopie_datei, stammdaten.fs_kopie_typ, stammdaten.fs_kopie_am = "", "", None
    if speichern:
        stammdaten.save()


def stammdaten_leeren(heute: dt.date | None = None) -> int:
    """Leert die persönlichen Angaben gesperrter Konten nach der Frist. Liefert die Anzahl."""
    heute = heute or timezone.localdate()
    jahre = PersonalEinstellungen.laden().stammdaten_loeschen_jahre
    grenze = monate_spaeter(heute, -12 * jahre)
    faellig = Stammdaten.objects.filter(benutzer__is_active=False, geleert_am__isnull=True).filter(
        Q(austritt__lt=grenze) | Q(austritt__isnull=True, benutzer__gesperrt_am__date__lt=grenze)
    )
    werte = {f: "" for f in PERSOENLICHE_FELDER} | {f: None for f in PERSOENLICHE_DATEN}
    anzahl = 0
    for s in faellig.select_related("benutzer"):
        with transaction.atomic(), disable_auditlog():
            kopie_loeschen(s, speichern=False)
            for feld, wert in werte.items():
                setattr(s, feld, wert)
            s.geleert_am = timezone.now()
            s.save()
            schulungen = list(s.benutzer.schulungen.values_list("pk", flat=True))
            s.benutzer.schulungen.all().delete()
            # Frühere Einträge im Änderungsprotokoll enthielten die Angaben noch.
            for modell, schluessel in ((Stammdaten, [s.pk]), (Schulung, schulungen)):
                LogEntry.objects.filter(
                    content_type=ContentType.objects.get_for_model(modell),
                    object_pk__in=[str(k) for k in schluessel],
                ).delete()
        anzahl += 1
    return anzahl
