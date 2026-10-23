"""Kundenstamm (Modul 2). Fachliche Grundlage: docs/fachkonzept.md, Import: docs/importformat.md."""

import datetime as dt

from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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
        "Interne Bemerkungen importieren",
        default=False,
        help_text="Freitext enthält oft Sensibles. Nur einschalten, wenn er gebraucht wird.",
    )
    kind_bis_alter = models.PositiveSmallIntegerField(
        "Kind bis unter … Jahren",
        default=18,
        help_text="Personen unter diesem Alter zählen als Kind.",
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
    # Nur gesetzt, wenn der Import keine einzelnen Angehörigen enthält.
    anzahl_erwachsene = models.PositiveSmallIntegerField("Erwachsene", null=True, blank=True)
    anzahl_kinder = models.PositiveSmallIntegerField("Kinder", null=True, blank=True)
    zusatz = models.JSONField("Zusatzfelder", default=dict, blank=True)
    importiert_am = models.DateTimeField("Importiert am", default=timezone.now)

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
        verbose_name = "Interne Bemerkung"
        verbose_name_plural = "Interne Bemerkungen"
        ordering = ["-datum"]

    def __str__(self):
        return f"Bemerkung vom {self.datum:%d.%m.%Y}"


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
):
    auditlog.register(modell)
