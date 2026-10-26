"""Kundenstamm (Modul 2). Fachliche Grundlage: docs/fachkonzept.md, Import: docs/importformat.md."""

import calendar
import datetime as dt
import uuid

from auditlog.context import disable_auditlog
from auditlog.registry import auditlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from apps.core import privatdateien
from apps.core.auswahl import GRUPPENFARBEN, NACHRICHT_ANLIEGEN
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
    export_felder = models.JSONField(
        "Spalten der Kundenliste und des Exports", default=list, blank=True,
        help_text="Leer = Kundennummer, Name, Kundengruppe, Ausgabetage, Uhrzeit, Personen, "
        "Status, Ausweis, letzter Besuch.",
    )  # fmt: skip
    historie_aufbewahren_jahre = models.PositiveSmallIntegerField(
        "Historie aufbewahren (Jahre)",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Ältere Einträge der Historie werden automatisch gelöscht.",
    )
    gruppe_behalten = models.BooleanField(
        "Kunden ohne gültigen Ausweis in der Kundengruppe lassen", default=False,
        help_text="Aus: Wer pausiert, gesperrt oder beendet ist oder keinen gültigen Ausweis mehr "
        "hat, fällt sofort aus der Kundengruppe, damit das Maximum der Gruppe stimmt.",
    )  # fmt: skip
    zugriffe_aufbewahren_tage = models.PositiveSmallIntegerField(
        "Zugriffsprotokoll aufbewahren (Tage)",
        default=365,
        validators=[MinValueValidator(30), MaxValueValidator(3650)],
        help_text="Einträge, wer welchen Haushalt angesehen hat, werden danach gelöscht.",
    )
    ausweis_gueltig_monate = models.PositiveSmallIntegerField(
        "Ausweis gültig für … Monate (Vorschlag bei der Aufnahme)",
        default=12,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    ausweis_bis_monatsende = models.BooleanField(
        "Gültigkeit bis zum Monatsende", default=True,
        help_text="z. B. Aufnahme am 24.10.2026, 12 Monate: gültig bis 31.10.2027.",
    )  # fmt: skip

    # Sammel-Verlängerung der Ausweise (ADR 0068)
    class Verlaengern(models.TextChoices):
        OHNE = "ohne", "ohne Bedingung (jeder Haushalt kann verlängern)"
        ALLE = "alle", "jede Person im Haushalt erfüllt eine Bedingung"
        EINE = "eine", "mindestens eine Person erfüllt eine Bedingung"

    verlaengern_regel = models.CharField(
        "Verlängern nur, wenn", max_length=5, choices=Verlaengern.choices, default=Verlaengern.OHNE,
        help_text="Bedingungen darunter. Wer sie nicht erfüllt, wird bei der Sammel-Verlängerung "
        "nicht verlängert.",
    )  # fmt: skip
    verlaengern_ab_alter = models.PositiveSmallIntegerField(
        "Bedingung: Alter ab", null=True, blank=True, default=60,
        validators=[MaxValueValidator(120)], help_text="Leer = Alter zählt nicht.",
    )  # fmt: skip
    verlaengern_felder = models.ManyToManyField(
        "Zusatzfeld", blank=True, related_name="+", verbose_name="Bedingung: Ja/Nein-Zusatzfelder",
        limit_choices_to={"typ": "ja_nein"},
        help_text="z. B. „Schwerbehindert“. Gilt das Feld für den Haushalt, zählt es für alle "
        "Personen.",
    )  # fmt: skip
    verlaengern_einkommensarten = models.ManyToManyField(
        "Einkommensart", blank=True, related_name="+",
        verbose_name="Bedingung: Einkommensarten",
        help_text="Hat der Haushalt eine dieser Einkommensarten, erfüllen alle Personen die "
        "Bedingung (z. B. „Grundsicherung im Alter“).",
    )  # fmt: skip

    class Ablehnung(models.TextChoices):
        NOTIZ = "notiz", "Notiz an die Ausgabestelle: Bedingung nicht erfüllt, Pause einlegen"
        PAUSIEREN = "pausieren", "Status „pausiert“ setzen und Notiz schreiben"
        ANZEIGEN = "anzeigen", "nur anzeigen, nichts ändern"

    verlaengern_ablehnung = models.CharField(
        "Wer die Bedingung nicht erfüllt", max_length=10, choices=Ablehnung.choices,
        default=Ablehnung.NOTIZ,
        help_text="Die gemeldete Notiz (z. B. „Bescheide geprüft …“) wird dabei gestrichen. Bei "
        "„Notiz“ bleibt der Status; der Ausweis läuft zu seinem Datum ab, und der Kunde fällt "
        "dann aus der Kundengruppe.",
    )  # fmt: skip
    verlaengern_sonst_pausieren_monate = models.PositiveSmallIntegerField(
        "Pause in Monaten", default=12, validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Steht in der Notiz an die Ausgabestelle (12 = „Pausenjahr“) bzw. bestimmt, bis "
        "wann pausiert wird.",
    )  # fmt: skip

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
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    anmerkung = models.TextField(
        "Allgemeine Anmerkungen", blank=True,
        help_text="Z. B. Zugang, Parken, Barrierefreiheit, Schlüssel, Besonderheiten.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Ausgabestelle"
        verbose_name_plural = "Ausgabestellen"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def anschrift(self) -> str:
        return ", ".join(t for t in (self.strasse, f"{self.plz} {self.ort}".strip()) if t)


class AusgabestelleZeit(models.Model):
    """Regelmäßige Zeit an einer Ausgabestelle (Ausgabe, Anlieferung …)."""

    class Wochentag(models.IntegerChoices):
        MO, DI, MI, DO, FR, SA, SO = (
            (0, "Montag"),
            (1, "Dienstag"),
            (2, "Mittwoch"),
            (3, "Donnerstag"),
            (4, "Freitag"),
            (5, "Samstag"),
            (6, "Sonntag"),
        )

    ausgabestelle = models.ForeignKey(Ausgabestelle, on_delete=models.CASCADE,
                                      related_name="zeiten")  # fmt: skip
    wochentag = models.PositiveSmallIntegerField("Wochentag", choices=Wochentag.choices)
    von = models.TimeField("von")
    bis = models.TimeField("bis", null=True, blank=True)
    art = models.CharField("Art", max_length=50, default="Ausgabe")
    hinweis = models.CharField("Hinweis", max_length=100, blank=True,
                               help_text="Z. B. „nur in geraden Kalenderwochen“.")  # fmt: skip

    class Meta:
        verbose_name = "Zeit der Ausgabestelle"
        verbose_name_plural = "Zeiten der Ausgabestellen"
        ordering = ["wochentag", "von"]

    def __str__(self):
        bis = f"–{self.bis:%H:%M}" if self.bis else ""
        return f"{self.get_wochentag_display()} {self.von:%H:%M}{bis} {self.art}"


class AusgabestelleKontakt(models.Model):
    """Ansprechpartner einer Ausgabestelle: registrierte Mitarbeitende oder extern (Name)."""

    ausgabestelle = models.ForeignKey(Ausgabestelle, on_delete=models.CASCADE,
                                      related_name="kontakte")  # fmt: skip
    zustaendigkeit = models.CharField("Zuständigkeit", max_length=50)
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ausgabestellen_kontakte", verbose_name="Mitarbeiter/in",
    )  # fmt: skip
    name = models.CharField(
        "Name (extern)", max_length=150, blank=True,
        help_text="Nur, wenn die Person kein Konto in bintafeln hat.",
    )  # fmt: skip
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)

    class Meta:
        verbose_name = "Ansprechpartner der Ausgabestelle"
        verbose_name_plural = "Ansprechpartner der Ausgabestellen"
        ordering = ["pk"]

    def __str__(self):
        return f"{self.anzeige_name} ({self.zustaendigkeit})"

    @property
    def anzeige_name(self) -> str:
        if self.benutzer_id:
            return self.benutzer.get_full_name() or self.benutzer.get_username()
        return self.name

    @property
    def anzeige_email(self) -> str:
        return self.email or (self.benutzer.email if self.benutzer_id else "")

    def clean(self):
        if not self.benutzer_id and not self.name.strip():
            raise ValidationError("Bitte Mitarbeiter/in wählen oder einen Namen eintragen.")


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
    farbe = models.CharField(
        "Farbe", max_length=10, blank=True, choices=GRUPPENFARBEN,
        help_text="Zur schnellen Erkennung am Einlass.",
    )  # fmt: skip
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
    aufgenommen_am = models.DateTimeField(
        "In bintafeln aufgenommen am", null=True, blank=True,
        help_text="Gesetzt vom Aufnahme-Assistenten; der Import-Abgleich fragt dann nach.",
    )  # fmt: skip
    geaendert_am = models.DateTimeField("In bintafeln geändert am", null=True, blank=True)
    geaendert_von = models.CharField("In bintafeln geändert von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Haushalt"
        verbose_name_plural = "Haushalte"
        ordering = ["kundennummer"]

    def __str__(self):
        return f"Haushalt {self.kundennummer}"

    def besuch_uhrzeit(self):
        """Uhrzeit der letzten Abholung am Tag des letzten Besuchs, falls bekannt."""
        if not self.letzter_besuch:
            return None
        if hasattr(self, "besuch_zeit"):  # aus der Liste (Subquery), spart Abfragen
            return self.besuch_zeit
        a = (self.abholungen.filter(datum=self.letzter_besuch, uhrzeit__isnull=False)
             .order_by("-uhrzeit").first())  # fmt: skip
        return a.uhrzeit if a else None

    @property
    def letzter_besuch_text(self) -> str:
        """„24.10.2026 13:40“, ohne bekannte Uhrzeit nur das Datum, sonst leer."""
        if not self.letzter_besuch:
            return ""
        zeit = self.besuch_uhrzeit()
        return f"{self.letzter_besuch:%d.%m.%Y}" + (f" {zeit:%H:%M}" if zeit else "")

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
        """Mit Recht „Alle Notizen löschen“ immer; sonst nur eigene vom selben Tag (Versehen)."""
        from apps.konten import rollen

        if rollen.hat_recht(benutzer, "kunden.notizen_loeschen"):
            return True
        heute = timezone.localdate()
        return self.benutzer_id == benutzer.pk and timezone.localdate(self.erstellt_am) == heute


class NotizVorlage(models.Model):
    """Vorgefertigter Notiztext: am Einlass mit einem Knopf als Notiz gespeichert."""

    text = models.CharField("Text", max_length=200)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    aktiv = models.BooleanField("Aktiv", default=True)
    melden = models.CharField(
        "Meldet der Verwaltung", max_length=20, choices=NACHRICHT_ANLIEGEN, blank=True,
        help_text="Leer: nur Notiz. Sonst schickt der Knopf zusätzlich eine Nachricht mit diesem "
        "Anliegen, z. B. „Bescheid geprüft – Ausweis verlängern“ für die Sammel-Verlängerung.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Notiz-Vorlage"
        verbose_name_plural = "Notiz-Vorlagen"
        ordering = ["reihenfolge", "text"]

    def __str__(self):
        return self.text


class Nachricht(models.Model):
    """Nachricht einer Ausgabestelle an die Verwaltung zu einem Kunden, den sie nicht aufrufen darf
    (ADR 0062). Hängt an der Kundennummer; erledigte werden nach ``AUFBEWAHREN_TAGE`` gelöscht."""

    AUFBEWAHREN_TAGE = 90

    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    anliegen = models.CharField("Anliegen", max_length=20, choices=NACHRICHT_ANLIEGEN,
                                default="sonstiges")  # fmt: skip
    text = models.TextField("Nachricht", max_length=1000, blank=True)
    stelle = models.ForeignKey("Ausgabestelle", null=True, blank=True, on_delete=models.SET_NULL,
                               related_name="+", verbose_name="Ausgabestelle")  # fmt: skip
    erstellt_am = models.DateTimeField("Geschrieben am", default=timezone.now)
    von = models.CharField("Von", max_length=150, blank=True)
    erledigt_am = models.DateTimeField("Erledigt am", null=True, blank=True)
    erledigt_von = models.CharField("Erledigt von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Nachricht zu einem Kunden"
        verbose_name_plural = "Nachrichten zu Kunden"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"Nachricht zu {self.kundennummer}"


def verwaiste_notizen_loeschen() -> int:
    """Notizen zu Kundennummern, die es nicht mehr gibt."""
    vorhanden = Haushalt.objects.values("kundennummer")
    return Notiz.objects.exclude(kundennummer__in=vorhanden).delete()[0]


class Dokumentart(models.Model):
    """Art eines Dokuments zum Haushalt mit eigener Aufbewahrungsfrist (ADR 0030)."""

    bezeichnung = models.CharField("Bezeichnung", max_length=100, unique=True)
    aufbewahren_monate = models.PositiveSmallIntegerField(
        "Aufbewahren (Monate)",
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(240)],
        help_text="Gezählt ab dem Dokumentdatum, ohne Datum ab dem Hochladen. Danach wird das "
        "Dokument automatisch gelöscht.",
    )
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Dokumentart"
        verbose_name_plural = "Dokumentarten"
        ordering = ["bezeichnung"]

    def __str__(self):
        return self.bezeichnung


class HaushaltDokument(models.Model):
    """Dokument zu einem Haushalt, verschlüsselt unter MEDIA_ROOT/privat/ (ADR 0030).

    Hängt an der Kundennummer, damit es einen Import übersteht; gelöscht wird es nach der Frist
    seiner Dokumentart.
    """

    ORDNER = "kunden-dokumente"

    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    art = models.ForeignKey(Dokumentart, verbose_name="Dokumentart", on_delete=models.PROTECT)
    titel = models.CharField("Titel", max_length=200)
    datum = models.DateField("Dokumentdatum", null=True, blank=True)
    datei = models.CharField(max_length=200, editable=False)
    typ = models.CharField(max_length=100, editable=False)
    groesse = models.PositiveIntegerField("Größe (Bytes)", default=0, editable=False)
    hochgeladen_am = models.DateTimeField("Hochgeladen am", default=timezone.now)
    hochgeladen_von = models.CharField("Hochgeladen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Dokument zum Haushalt"
        verbose_name_plural = "Dokumente zu Haushalten"
        ordering = ["-hochgeladen_am"]

    def __str__(self):
        return self.titel

    @property
    def loeschen_am(self) -> dt.date:
        """Erster Tag, an dem das Dokument nicht mehr aufbewahrt wird."""
        beginn = self.datum or timezone.localdate(self.hochgeladen_am)
        jahr, monat = divmod(beginn.month - 1 + self.art.aufbewahren_monate, 12)
        jahr, monat = beginn.year + jahr, monat + 1
        letzter = calendar.monthrange(jahr, monat)[1]
        return dt.date(jahr, monat, min(beginn.day, letzter))

    def loeschen(self) -> None:
        """Datei und Eintrag entfernen."""
        privatdateien.loeschen(self.ORDNER, self.datei)
        self.delete()


def abgelaufene_dokumente_loeschen(heute: dt.date | None = None) -> int:
    heute = heute or timezone.localdate()
    anzahl = 0
    with disable_auditlog():  # Fristablauf ist kein fachliches Ereignis je Datensatz
        for d in HaushaltDokument.objects.select_related("art"):
            if d.loeschen_am <= heute:
                d.loeschen()
                anzahl += 1
    return anzahl


class HaushaltEreignis(models.Model):
    """Eine Zeile der Historie eines Haushalts (ADR 0031), an der Kundennummer."""

    class Quelle(models.TextChoices):
        IMPORT = "import", "Import"
        AUFNAHME = "aufnahme", "Aufnahme"
        BEARBEITUNG = "bearbeitung", "Bearbeitung"
        AUTOMATIK = "automatik", "automatisch"

    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    zeitpunkt = models.DateTimeField("Zeitpunkt", default=timezone.now, db_index=True)
    quelle = models.CharField("Quelle", max_length=12, choices=Quelle.choices)
    text = models.CharField("Änderung", max_length=300)
    von = models.CharField("Von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Eintrag der Historie"
        verbose_name_plural = "Historie"
        ordering = ["-zeitpunkt", "-id"]

    def __str__(self):
        return f"{self.kundennummer}: {self.text}"


class Gruppenzeit(models.Model):
    """Von wann bis wann ein Kunde in einer Kundengruppe war (an der Kundennummer, übersteht den
    Import). Gepflegt von ``apps.kunden.gruppen.zeiten_abgleichen()``."""

    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    kundengruppe = models.ForeignKey(Kundengruppe, on_delete=models.SET_NULL, null=True,
                                     blank=True, related_name="+")  # fmt: skip
    gruppe_name = models.CharField("Kundengruppe", max_length=100)
    von = models.DateField("von", null=True, blank=True,
                           help_text="Leer: schon vor der Einführung.")  # fmt: skip
    bis = models.DateField("bis", null=True, blank=True)
    grund = models.CharField("Grund für das Ende", max_length=200, blank=True)

    class Meta:
        verbose_name = "Zeit in einer Kundengruppe"
        verbose_name_plural = "Zeiten in Kundengruppen"
        ordering = ["-bis", "-von", "-pk"]
        indexes = [models.Index(fields=["kundennummer", "bis"])]

    def __str__(self):
        return f"{self.kundennummer} in {self.gruppe_name}"


def alte_historie_loeschen(heute: dt.date | None = None) -> int:
    heute = heute or timezone.localdate()
    jahre = KundenEinstellungen.laden().historie_aufbewahren_jahre
    try:
        tag = heute.replace(year=heute.year - jahre)
    except ValueError:  # 29. Februar
        tag = heute.replace(year=heute.year - jahre, day=28)
    grenze = timezone.make_aware(dt.datetime.combine(tag, dt.time()))
    return (HaushaltEreignis.objects.filter(zeitpunkt__lt=grenze).delete()[0]
            + Gruppenzeit.objects.filter(bis__lt=tag).delete()[0])  # fmt: skip


class AusweisVorlage(models.Model):
    """Gestaltung des Kundenausweises (Singleton, ADR 0027). Elemente siehe kunden.ausweis."""

    EINZIGE_ID = 1

    class Seitenformat(models.TextChoices):
        A4 = "a4", "A4 mit Schnittmarken (ein Ausweis je Blatt)"
        KARTE = "karte", "Kartengröße (für Kartendrucker)"

    name = models.CharField(
        "Ausweisname", max_length=100, default="Kundenausweis",
        help_text="z. B. „Tafelausweis Tafel Musterstadt“; als Element platzierbar.",
    )  # fmt: skip
    seitenformat = models.CharField(
        "Druck", max_length=5, choices=Seitenformat.choices, default=Seitenformat.A4
    )
    hintergrund = models.ImageField(
        "Hintergrundbild vorn", upload_to="oeffentlich/ausweis/", blank=True,
        help_text="PNG oder JPG, höchstens 2 MB; wird auf Kartengröße (85,6 × 54 mm) gestreckt.",
    )  # fmt: skip
    rueckseite_aktiv = models.BooleanField("Rückseite drucken", default=False)
    hintergrund_rueckseite = models.ImageField(
        "Hintergrundbild hinten", upload_to="oeffentlich/ausweis/", blank=True
    )
    vorderseite = models.JSONField("Elemente vorn", default=list, blank=True)
    rueckseite = models.JSONField("Elemente hinten", default=list, blank=True)
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        verbose_name = "Ausweis-Vorlage"
        verbose_name_plural = "Ausweis-Vorlage"

    def __str__(self):
        return f"Ausweis-Vorlage „{self.name}“"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "AusweisVorlage":
        vorlage, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return vorlage

    def elemente_vorne(self) -> list[dict]:
        from apps.kunden import ausweis

        return ausweis.elemente_pruefen(self.vorderseite) if self.vorderseite else (
            ausweis.standard())  # fmt: skip

    def elemente_hinten(self) -> list[dict]:
        """Rückseite: frei, ohne Pflicht-Elemente."""
        from apps.kunden import ausweis

        return [e for e in (ausweis.element_pruefen(r) for r in self.rueckseite or []) if e]


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
    export = models.BooleanField("Export der Kundenliste", default=False)

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
        + abgelaufene_dokumente_loeschen()
        + alte_historie_loeschen()
        + alte_nachrichten_loeschen()
        + _gruppenregel()
    )


def alte_nachrichten_loeschen() -> int:
    grenze = timezone.now() - dt.timedelta(days=Nachricht.AUFBEWAHREN_TAGE)
    return Nachricht.objects.filter(erledigt_am__lt=grenze).delete()[0]


def _gruppenregel() -> int:
    from apps.kunden import gruppen

    return gruppen.regel_anwenden()


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
    AusweisVorlage,
    Abholung,
    Ausnahme,
    ImportLauf,
    Dokumentart,
    AusgabestelleZeit,
    AusgabestelleKontakt,
):
    auditlog.register(modell)
auditlog.register(HaushaltDokument, exclude_fields=["datei"])
auditlog.register(Nachricht)
