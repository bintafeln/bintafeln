"""Kundenstamm (Modul 2). Fachliche Grundlage: docs/fachkonzept.md, Import: docs/importformat.md."""

import datetime as dt
import uuid

from auditlog.context import disable_auditlog
from auditlog.registry import auditlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from apps.kunden import werte


class KundenEinstellungen(models.Model):
    """Einstellungen des Kundenstamms je Tafel (Singleton)."""

    EINZIGE_ID = 1

    telefon_erfassen = models.BooleanField("Telefon erfassen", default=True)
    email_erfassen = models.BooleanField("E-Mail erfassen", default=True)
    staatsangehoerigkeit_erfassen = models.BooleanField(
        "Staatsangehörigkeit erfassen", default=True
    )
    familienstand_erfassen = models.BooleanField("Familienstand erfassen", default=True)
    bemerkungen_importieren = models.BooleanField(
        "Interne Anmerkungen importieren",
        default=False,
        help_text="Freitext enthält oft Sensibles. Nur einschalten, wenn er gebraucht wird.",
    )
    kind_bis_alter = models.PositiveSmallIntegerField(
        "Kind bis unter … Jahren",
        default=18,
        help_text="Personen unter diesem Alter zählen als Kind.",
    )
    abholungen_aufbewahren_jahre = models.PositiveSmallIntegerField(
        "Abholungen und Ausnahmen aufbewahren (Jahre)",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Ältere werden nicht importiert und automatisch gelöscht.",
    )
    zugriffe_aufbewahren_tage = models.PositiveSmallIntegerField(
        "Zugriffsprotokoll aufbewahren (Tage)",
        default=365,
        validators=[MinValueValidator(30), MaxValueValidator(3650)],
        help_text="Einträge, wer welchen Haushalt angesehen hat, werden danach gelöscht.",
    )
    besondere_kategorie_fuer_ausgabe = models.BooleanField(
        "Rolle Ausgabe sieht Zusatzfelder der besonderen Kategorie",
        default=False,
        help_text="Admin und Büro sehen sie immer. Jeder Zugriff wird protokolliert.",
    )

    class Meta:
        verbose_name = "Einstellungen Kundenstamm"
        verbose_name_plural = "Einstellungen Kundenstamm"

    def __str__(self):
        return "Einstellungen Kundenstamm"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "KundenEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


class Zusatzfeld(models.Model):
    """Von der Tafel selbst angelegtes Feld für Haushalte oder Personen."""

    class GiltFuer(models.TextChoices):
        HAUSHALT = "haushalt", "Haushalt"
        PERSON = "person", "jede Person"

    class Typ(models.TextChoices):
        JA_NEIN = "ja_nein", "Ja/Nein"
        AUSWAHL = "auswahl", "Auswahl"
        TEXT = "text", "Text"
        DATUM = "datum", "Datum"

    schluessel = models.CharField(
        "Schlüssel",
        max_length=40,
        unique=True,
        validators=[
            RegexValidator(
                r"^[a-z][a-z0-9_]*$",
                "Nur Kleinbuchstaben a–z, Ziffern und _, beginnend mit einem Buchstaben.",
            )
        ],
        help_text="Erscheint im Import als Spalte zusatz_<schlüssel>. Später nicht änderbar.",
    )
    bezeichnung = models.CharField("Bezeichnung", max_length=100)
    gilt_fuer = models.CharField(
        "Gilt für", max_length=10, choices=GiltFuer.choices, default=GiltFuer.PERSON
    )
    typ = models.CharField("Typ", max_length=10, choices=Typ.choices, default=Typ.JA_NEIN)
    optionen = models.TextField(
        "Auswahloptionen", blank=True, help_text="Nur für Typ Auswahl: eine Option je Zeile."
    )
    besondere_kategorie = models.BooleanField(
        "Besondere Kategorie (Art. 9 DSGVO)",
        default=False,
        help_text="Z. B. Gesundheitsdaten oder Angaben, die auf Religion schließen lassen. "
        "Nur berechtigte Rollen sehen das Feld, jeder Zugriff wird protokolliert. "
        "Dafür braucht die Tafel in der Regel eine ausdrückliche Einwilligung.",
    )
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Zusatzfeld"
        verbose_name_plural = "Zusatzfelder"
        ordering = ["reihenfolge", "bezeichnung"]

    def __str__(self):
        return self.bezeichnung

    def optionen_liste(self) -> list[str]:
        return [zeile.strip() for zeile in self.optionen.splitlines() if zeile.strip()]

    def clean(self):
        if self.typ == self.Typ.AUSWAHL and not self.optionen_liste():
            raise ValidationError({"optionen": "Für eine Auswahl bitte mindestens eine Option."})

    def wert_lesen(self, text: str):
        """Wandelt einen Text aus dem Import in den gespeicherten Wert um.

        Leerer Text ergibt None. Unpassende Werte lösen UngueltigerWert aus.
        """
        text = (text or "").strip()
        if not text:
            return None
        if self.typ == self.Typ.JA_NEIN:
            return werte.ja_nein(text)
        if self.typ == self.Typ.DATUM:
            return werte.datum(text).isoformat()
        if self.typ == self.Typ.AUSWAHL:
            for option in self.optionen_liste():
                if option.lower() == text.lower():
                    return option
            raise werte.UngueltigerWert(f"keine gültige Option: {text!r}")
        return text

    def wert_anzeigen(self, wert) -> str:
        """Gespeicherten Wert für die Anzeige aufbereiten; None ergibt einen leeren Text."""
        if wert is None or wert == "":
            return ""
        if self.typ == self.Typ.JA_NEIN:
            return "ja" if wert else "nein"
        if self.typ == self.Typ.DATUM:
            try:
                return dt.date.fromisoformat(wert).strftime("%d.%m.%Y")
            except (TypeError, ValueError):
                return str(wert)
        return str(wert)

    @property
    def import_spalte(self) -> str:
        return f"zusatz_{self.schluessel}"


class Ausgabestelle(models.Model):
    name = models.CharField("Name", max_length=100, unique=True)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Ausgabestelle"
        verbose_name_plural = "Ausgabestellen"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Kundengruppe(models.Model):
    """Fester Abholtermin an einer Ausgabestelle."""

    kuerzel = models.CharField("Kürzel", max_length=20, blank=True)
    name = models.CharField("Name", max_length=100, unique=True)
    ausgabestelle = models.ForeignKey(
        Ausgabestelle,
        verbose_name="Ausgabestelle",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
    )
    wochentage = models.CharField("Wochentage", max_length=30, blank=True)
    uhrzeit = models.TimeField("Uhrzeit", null=True, blank=True)
    maximum = models.PositiveIntegerField("Maximum Haushalte", null=True, blank=True)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Kundengruppe"
        verbose_name_plural = "Kundengruppen"
        ordering = ["kuerzel", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["kuerzel"],
                condition=~models.Q(kuerzel=""),
                name="kundengruppe_kuerzel_eindeutig",
            )
        ]

    def __str__(self):
        return f"{self.kuerzel} – {self.name}" if self.kuerzel else self.name


class Einkommensart(models.Model):
    bezeichnung = models.CharField("Bezeichnung", max_length=100, unique=True)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Einkommensart"
        verbose_name_plural = "Einkommensarten"
        ordering = ["bezeichnung"]

    def __str__(self):
        return self.bezeichnung


class Haushalt(models.Model):
    class Status(models.TextChoices):
        AKTIV = "aktiv", "aktiv"
        PAUSIERT = "pausiert", "pausiert"
        GESPERRT = "gesperrt", "gesperrt"
        BEENDET = "beendet", "beendet"

    kundennummer = models.CharField("Kundennummer", max_length=20, unique=True)
    status = models.CharField("Status", max_length=10, choices=Status.choices, default=Status.AKTIV)
    kundengruppe = models.ForeignKey(
        Kundengruppe,
        verbose_name="Kundengruppe",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="haushalte",
    )
    kunde_seit = models.DateField("Kunde seit", null=True, blank=True)
    ausweis_gueltig_bis = models.DateField("Ausweis gültig bis", null=True, blank=True)
    letzter_besuch = models.DateField("Letzter Besuch", null=True, blank=True)
    einkommensart = models.ForeignKey(
        Einkommensart,
        verbose_name="Einkommensart",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    kontostand = models.DecimalField(
        "Kontostand (Euro)",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Stand des Kundenkontos laut Import. Buchungen folgen mit der Ausgabe.",
    )
    # Nur gesetzt, wenn der Import keine einzelnen Angehörigen enthält.
    anzahl_erwachsene = models.PositiveSmallIntegerField("Erwachsene", null=True, blank=True)
    anzahl_kinder = models.PositiveSmallIntegerField("Kinder", null=True, blank=True)
    zusatz = models.JSONField("Zusatzfelder", default=dict, blank=True)
    importiert_am = models.DateTimeField("Importiert am", default=timezone.now)
    # In bintafeln von Hand geändert (ADR 0025); der nächste Import ersetzt die Änderungen.
    geaendert_am = models.DateTimeField("In bintafeln geändert am", null=True, blank=True)
    geaendert_von = models.CharField("In bintafeln geändert von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Haushalt"
        verbose_name_plural = "Haushalte"
        ordering = ["kundennummer"]

    def __str__(self):
        return f"Haushalt {self.kundennummer}"

    @property
    def hauptperson(self):
        return self.personen.filter(ist_hauptperson=True).first()

    def groesse(self, kind_bis_alter: int, stichtag: dt.date | None = None) -> tuple[int, int]:
        """(Erwachsene, Kinder). Ohne Altersangabe zählt eine Person als erwachsen."""
        personen = list(self.personen.all())
        if len(personen) <= 1 and (self.anzahl_erwachsene or self.anzahl_kinder):
            return self.anzahl_erwachsene or 0, self.anzahl_kinder or 0
        kinder = sum(1 for p in personen if p.ist_kind(kind_bis_alter, stichtag))
        return len(personen) - kinder, kinder


class Person(models.Model):
    haushalt = models.ForeignKey(Haushalt, on_delete=models.CASCADE, related_name="personen")
    ist_hauptperson = models.BooleanField("Hauptperson", default=False)
    anrede = models.CharField("Anrede", max_length=30, blank=True)
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    staatsangehoerigkeit = models.CharField("Staatsangehörigkeit", max_length=100, blank=True)
    familienstand = models.CharField("Familienstand", max_length=50, blank=True)
    zusatz = models.JSONField("Zusatzfelder", default=dict, blank=True)

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Personen"
        ordering = ["-ist_hauptperson", "geburtsdatum", "nachname", "vorname"]
        constraints = [
            models.UniqueConstraint(
                fields=["haushalt"],
                condition=models.Q(ist_hauptperson=True),
                name="eine_hauptperson_je_haushalt",
            )
        ]

    def __str__(self):
        return f"{self.vorname} {self.nachname}"

    def alter(self, stichtag: dt.date | None = None) -> int | None:
        if self.geburtsdatum is None:
            return None
        stichtag = stichtag or timezone.localdate()
        g = self.geburtsdatum
        return stichtag.year - g.year - ((stichtag.month, stichtag.day) < (g.month, g.day))

    def ist_kind(self, kind_bis_alter: int, stichtag: dt.date | None = None) -> bool:
        alter = self.alter(stichtag)
        return alter is not None and alter < kind_bis_alter


class Abholer(models.Model):
    haushalt = models.ForeignKey(Haushalt, on_delete=models.CASCADE, related_name="abholer")
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    eigene_kundennummer = models.CharField("Eigene Kundennummer", max_length=20, blank=True)

    class Meta:
        verbose_name = "Abholberechtigte Person"
        verbose_name_plural = "Abholberechtigte"

    def __str__(self):
        return f"{self.vorname} {self.nachname}"


class Sperre(models.Model):
    haushalt = models.ForeignKey(Haushalt, on_delete=models.CASCADE, related_name="sperren")
    von = models.DateField("Von")
    bis = models.DateField("Bis", null=True, blank=True)
    begruendung = models.TextField("Begründung", blank=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=100, blank=True)

    class Meta:
        verbose_name = "Sperre"
        verbose_name_plural = "Sperren"
        ordering = ["-von"]

    def __str__(self):
        return f"Sperre ab {self.von:%d.%m.%Y}"

    def ist_aktiv(self, stichtag: dt.date | None = None) -> bool:
        stichtag = stichtag or timezone.localdate()
        return self.von <= stichtag and (self.bis is None or stichtag <= self.bis)


class Bemerkung(models.Model):
    haushalt = models.ForeignKey(Haushalt, on_delete=models.CASCADE, related_name="bemerkungen")
    datum = models.DateField("Datum")
    text = models.TextField("Text")
    verfasst_von = models.CharField("Verfasst von", max_length=100, blank=True)

    class Meta:
        verbose_name = "Interne Anmerkung"
        verbose_name_plural = "Interne Anmerkungen"
        ordering = ["-datum"]

    def __str__(self):
        return f"Anmerkung vom {self.datum:%d.%m.%Y}"


class Notiz(models.Model):
    """Notiz zu einem Haushalt, in bintafeln geschrieben (Einlass, Büro, Admin).

    Hängt an der Kundennummer, nicht am Datensatz: Der Import ersetzt die Haushalte, die
    Notizen bleiben. Gibt es die Kundennummer nicht mehr, werden sie gelöscht.
    """

    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    text = models.TextField("Notiz", max_length=1000)
    erstellt_am = models.DateTimeField("Geschrieben am", default=timezone.now)
    verfasst_von = models.CharField("Verfasst von", max_length=100, blank=True)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Geschrieben von (Konto)",
    )  # fmt: skip

    class Meta:
        verbose_name = "Notiz"
        verbose_name_plural = "Notizen"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"Notiz vom {timezone.localtime(self.erstellt_am):%d.%m.%Y}"

    def darf_loeschen(self, benutzer) -> bool:
        """Admin und Büro immer; sonst nur eigene Notizen vom selben Tag (Versehen)."""
        from apps.konten import rollen

        if rollen.hat_rolle(benutzer, rollen.ADMIN, rollen.BUERO):
            return True
        heute = timezone.localdate()
        return self.benutzer_id == benutzer.pk and timezone.localdate(self.erstellt_am) == heute


class NotizVorlage(models.Model):
    """Vorgefertigter Notiztext: am Einlass mit einem Knopf als Notiz gespeichert."""

    text = models.CharField("Text", max_length=200)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Notiz-Vorlage"
        verbose_name_plural = "Notiz-Vorlagen"
        ordering = ["reihenfolge", "text"]

    def __str__(self):
        return self.text


def verwaiste_notizen_loeschen() -> int:
    """Notizen zu Kundennummern, die es nicht mehr gibt."""
    vorhanden = Haushalt.objects.values("kundennummer")
    return Notiz.objects.exclude(kundennummer__in=vorhanden).delete()[0]


class Abholung(models.Model):
    """Eine Abholung. Wird nach der Aufbewahrungsfrist der Einstellungen gelöscht."""

    haushalt = models.ForeignKey(Haushalt, on_delete=models.CASCADE, related_name="abholungen")
    datum = models.DateField("Datum")
    uhrzeit = models.TimeField("Uhrzeit", null=True, blank=True)
    beitrag = models.DecimalField("Beitrag", max_digits=8, decimal_places=2, null=True, blank=True)
    ausgabestelle = models.ForeignKey(
        Ausgabestelle,
        verbose_name="Ausgabestelle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    eingetragen_von = models.CharField("Eingetragen von", max_length=100, blank=True)
    erfasst_am = models.DateTimeField(
        "In bintafeln erfasst am",
        null=True,
        blank=True,
        help_text="Leer, wenn aus dem Import übernommen.",
    )

    class Meta:
        verbose_name = "Abholung"
        verbose_name_plural = "Abholungen"
        ordering = ["-datum", "-uhrzeit"]

    def __str__(self):
        return f"Abholung am {self.datum:%d.%m.%Y}"


class Ausnahme(models.Model):
    """Erlaubt eine Abholung trotz Regel, z. B. außerhalb des eigenen Termins."""

    haushalt = models.ForeignKey(Haushalt, on_delete=models.CASCADE, related_name="ausnahmen")
    datum = models.DateField("Datum")
    begruendung = models.TextField("Begründung", blank=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=100, blank=True)
    erfasst_am = models.DateTimeField(
        "In bintafeln erfasst am",
        null=True,
        blank=True,
        help_text="Leer, wenn aus dem Import übernommen.",
    )

    class Meta:
        verbose_name = "Ausnahme"
        verbose_name_plural = "Ausnahmen"
        ordering = ["-datum"]

    def __str__(self):
        return f"Ausnahme am {self.datum:%d.%m.%Y}"


def abholfrist_beginn(heute: dt.date | None = None) -> dt.date:
    """Ältester Tag, an dem Abholungen und Ausnahmen noch aufbewahrt werden."""
    heute = heute or timezone.localdate()
    jahre = KundenEinstellungen.laden().abholungen_aufbewahren_jahre
    try:
        return heute.replace(year=heute.year - jahre)
    except ValueError:  # 29. Februar
        return heute.replace(year=heute.year - jahre, day=28)


def abgelaufene_abholungen_loeschen(heute: dt.date | None = None) -> int:
    """Löscht Abholungen und Ausnahmen, deren Aufbewahrungsfrist abgelaufen ist."""
    beginn = abholfrist_beginn(heute)
    anzahl = 0
    with disable_auditlog():  # Fristablauf ist kein fachliches Ereignis je Datensatz
        for modell in (Abholung, Ausnahme):
            anzahl += modell.objects.filter(datum__lt=beginn).delete()[0]
    return anzahl


class Zugriff(models.Model):
    """Wer hat wann die Detailseite welches Haushalts angesehen (Zugriffsprotokoll).

    Hängt an der Kundennummer, nicht am Datensatz, damit es einen Import übersteht.
    """

    zeitpunkt = models.DateTimeField("Zeitpunkt", default=timezone.now, db_index=True)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Benutzer", null=True, on_delete=models.SET_NULL
    )
    benutzername = models.CharField("Benutzername", max_length=150)
    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    besondere_kategorie = models.BooleanField("Mit Angaben der besonderen Kategorie", default=False)

    class Meta:
        verbose_name = "Zugriff"
        verbose_name_plural = "Zugriffe"
        ordering = ["-zeitpunkt"]

    def __str__(self):
        return f"Zugriff auf {self.kundennummer} durch {self.benutzername}"


def abgelaufene_zugriffe_loeschen() -> int:
    tage = KundenEinstellungen.laden().zugriffe_aufbewahren_tage
    grenze = timezone.now() - dt.timedelta(days=tage)
    return Zugriff.objects.filter(zeitpunkt__lt=grenze).delete()[0]


def fristen_anwenden() -> int:
    """Löscht alles, dessen Aufbewahrungsfrist abgelaufen ist. Liefert die Anzahl."""
    return (
        abgelaufene_abholungen_loeschen()
        + abgelaufene_zugriffe_loeschen()
        + verwaiste_notizen_loeschen()
    )


class ImportVorbereitung(models.Model):
    """Geprüfte Importdaten bis zur Bestätigung. Wird spätestens nach einer Stunde gelöscht."""

    GUELTIG = dt.timedelta(hours=1)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    erstellt_am = models.DateTimeField(default=timezone.now)
    dateien = models.JSONField(default=list)
    pruefsumme = models.CharField(max_length=64)
    daten = models.JSONField()
    bericht = models.JSONField(default=list)

    class Meta:
        verbose_name = "Import in Vorbereitung"
        verbose_name_plural = "Importe in Vorbereitung"

    def __str__(self):
        return f"Import in Vorbereitung vom {timezone.localtime(self.erstellt_am):%d.%m.%Y %H:%M}"

    @property
    def abgelaufen(self) -> bool:
        return timezone.now() - self.erstellt_am > self.GUELTIG

    @classmethod
    def abgelaufene_loeschen(cls) -> int:
        anzahl, _ = cls.objects.filter(erstellt_am__lt=timezone.now() - cls.GUELTIG).delete()
        return anzahl


class ImportLauf(models.Model):
    """Protokoll eines durchgeführten Imports, ohne Inhalte."""

    zeitpunkt = models.DateTimeField("Zeitpunkt", default=timezone.now)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Durchgeführt von",
        null=True,
        on_delete=models.SET_NULL,
    )
    dateien = models.JSONField("Dateien", default=list)
    pruefsumme = models.CharField("Prüfsumme (SHA-256)", max_length=64)
    anzahl_haushalte = models.PositiveIntegerField("Haushalte", default=0)
    anzahl_personen = models.PositiveIntegerField("Personen", default=0)
    anzahl_abholer = models.PositiveIntegerField("Abholberechtigte", default=0)
    anzahl_sperren = models.PositiveIntegerField("Sperren", default=0)
    anzahl_bemerkungen = models.PositiveIntegerField("Anmerkungen", default=0)
    anzahl_abholungen = models.PositiveIntegerField("Abholungen", default=0)
    anzahl_ausnahmen = models.PositiveIntegerField("Ausnahmen", default=0)
    anzahl_warnungen = models.PositiveIntegerField("Warnungen", default=0)

    class Meta:
        verbose_name = "Import"
        verbose_name_plural = "Importe"
        ordering = ["-zeitpunkt"]

    def __str__(self):
        return f"Import vom {timezone.localtime(self.zeitpunkt):%d.%m.%Y %H:%M}"


for modell in (
    KundenEinstellungen,
    Zusatzfeld,
    Ausgabestelle,
    Kundengruppe,
    Einkommensart,
    Haushalt,
    Person,
    Abholer,
    Sperre,
    Bemerkung,
    Notiz,
    NotizVorlage,
    Abholung,
    Ausnahme,
    ImportLauf,
):
    auditlog.register(modell)
