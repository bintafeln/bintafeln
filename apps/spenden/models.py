"""Spenden und Zuwendungsbestätigungen (Modul 5, ADR 0045)."""

from decimal import Decimal

from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.adressen.models import Adresse


class SpendenEinstellungen(models.Model):
    """Angaben der Tafel für Zuwendungsbestätigungen (Singleton)."""

    class Grundlage(models.TextChoices):
        FREISTELLUNG = "freistellung", "Freistellungsbescheid"
        ANLAGE = "anlage", "Anlage zum Körperschaftsteuerbescheid"
        FESTSTELLUNG = "feststellung", "Feststellung nach § 60a AO (neu gegründet)"

    EINZIGE_ID = 1
    koerperschaft = models.CharField(
        "Name der Körperschaft", max_length=200, blank=True,
        help_text="Leer = Name der Tafel aus den Einstellungen.",
    )  # fmt: skip
    anschrift = models.CharField("Anschrift der Körperschaft", max_length=300, blank=True,
                                 help_text="Leer = Anschrift der Tafel.")  # fmt: skip
    zwecke = models.TextField(
        "Steuerbegünstigte Zwecke", blank=True,
        help_text="Wörtlich wie im Bescheid, z. B. „mildtätige Zwecke im Sinne des § 53 AO“.",
    )  # fmt: skip
    grundlage = models.CharField(
        "Grundlage der Steuerbegünstigung",
        max_length=15,
        choices=Grundlage.choices,
        default=Grundlage.FREISTELLUNG,
    )
    finanzamt = models.CharField("Finanzamt", max_length=200, blank=True)
    steuernummer = models.CharField("Steuernummer", max_length=50, blank=True)
    bescheid_vom = models.DateField("Datum des Bescheids", null=True, blank=True)
    veranlagungszeitraum = models.CharField(
        "Veranlagungszeitraum", max_length=50, blank=True,
        help_text="Nur bei Freistellungsbescheid/Anlage, z. B. „2021 bis 2023“.",
    )  # fmt: skip
    mitgliedsbeitraege_abziehbar = models.BooleanField(
        "Mitgliedsbeiträge sind abziehbar", default=True,
        help_text="Bei mildtätigen Zwecken in der Regel ja (§ 10b Abs. 1 EStG). Im Zweifel "
        "Steuerberatung fragen.",
    )  # fmt: skip
    unterzeichnet_von = models.CharField(
        "Unterschrift: Name und Funktion", max_length=200, blank=True,
        help_text="Z. B. „Erika Muster, Kassenwartin“.",
    )  # fmt: skip
    ort = models.CharField("Ort für Ort und Datum", max_length=100, blank=True,
                           help_text="Leer = Ort der Tafel.")  # fmt: skip
    naechste_nummer = models.PositiveIntegerField("Nächste Bestätigungsnummer", default=1)

    class Meta:
        verbose_name = "Einstellungen für Spenden"
        verbose_name_plural = "Einstellungen für Spenden"

    def __str__(self):
        return "Einstellungen für Spenden"

    @classmethod
    def laden(cls):
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    def fehlende_angaben(self) -> list[str]:
        """Was für eine Zuwendungsbestätigung noch fehlt."""
        felder = [("zwecke", "steuerbegünstigte Zwecke"), ("finanzamt", "Finanzamt"),
                  ("steuernummer", "Steuernummer"), ("bescheid_vom", "Datum des Bescheids"),
                  ("unterzeichnet_von", "Unterschrift")]  # fmt: skip
        if self.grundlage != self.Grundlage.FESTSTELLUNG:
            felder.append(("veranlagungszeitraum", "Veranlagungszeitraum"))
        return [name for feld, name in felder if not getattr(self, feld)]


class Zuwendungsbestaetigung(models.Model):
    class Art(models.TextChoices):
        GELD = "geld", "Geldzuwendung"
        SAMMEL = "sammel", "Sammelbestätigung über Geldzuwendungen"
        SACH = "sach", "Sachzuwendung"

    nummer = models.PositiveIntegerField("Nummer", unique=True)
    art = models.CharField("Art", max_length=10, choices=Art.choices)
    adresse = models.ForeignKey(Adresse, on_delete=models.PROTECT, related_name="bestaetigungen")
    ausgestellt_am = models.DateField("Ausgestellt am")
    betrag = models.DecimalField("Betrag", max_digits=12, decimal_places=2)
    ausgestellt_von = models.CharField("Ausgestellt von", max_length=150, blank=True)
    storniert_am = models.DateTimeField("Storniert am", null=True, blank=True)
    storniert_von = models.CharField("Storniert von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Zuwendungsbestätigung"
        verbose_name_plural = "Zuwendungsbestätigungen"
        ordering = ["-nummer"]

    def __str__(self):
        return f"Zuwendungsbestätigung Nr. {self.nummer}"


class Spende(models.Model):
    class Art(models.TextChoices):
        GELD = "geld", "Geldspende"
        SACH = "sach", "Sachspende"

    class Herkunft(models.TextChoices):
        PRIVAT = "privat", "Privatvermögen"
        BETRIEB = "betrieb", "Betriebsvermögen"
        UNBEKANNT = "unbekannt", "keine Angabe trotz Aufforderung"

    art = models.CharField("Art", max_length=5, choices=Art.choices, default=Art.GELD)
    adresse = models.ForeignKey(Adresse, on_delete=models.PROTECT, related_name="spenden",
                                verbose_name="Spender")  # fmt: skip
    datum = models.DateField("Datum der Zuwendung")
    betrag = models.DecimalField(
        "Betrag / Wert (Euro)", max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Bei Sachspenden der Wert; ohne Wert keine Zuwendungsbestätigung möglich.",
    )  # fmt: skip
    mitgliedsbeitrag = models.BooleanField("Mitgliedsbeitrag", default=False)
    zahlungsweg = models.CharField("Zahlungsweg", max_length=30, blank=True)
    verzicht_aufwand = models.BooleanField(
        "Verzicht auf Erstattung von Aufwendungen", default=False,
        help_text="„Aufwandsspende“, z. B. nicht abgerechnete Fahrtkosten.",
    )  # fmt: skip
    beschreibung = models.CharField(
        "Bezeichnung", max_length=300, blank=True,
        help_text="Bei Sachspenden: was genau, z. B. „12 Kisten Obst und Gemüse“, mit Zustand.",
    )  # fmt: skip
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, null=True, blank=True)
    einheit = models.CharField("Einheit", max_length=30, blank=True)
    herkunft = models.CharField("Herkunft (Sachspende)", max_length=10,
                                choices=Herkunft.choices, blank=True)  # fmt: skip
    unterlagen = models.BooleanField(
        "Unterlagen zur Wertermittlung liegen vor", default=False,
        help_text="Z. B. Rechnung oder Gutachten (Sachspende).",
    )  # fmt: skip
    zweck = models.CharField("Zweck / Anmerkung", max_length=200, blank=True)
    belegnummer = models.CharField(
        "Belegnummer", max_length=50, blank=True,
        help_text="Z. B. die Nummer im Vereinsportal oder auf dem Kontoauszug. Beim Import wird "
        "eine Spende mit derselben Belegnummer nicht noch einmal angelegt.",
    )  # fmt: skip
    bestaetigung = models.ForeignKey(
        Zuwendungsbestaetigung, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="spenden", editable=False,
    )  # fmt: skip
    eingetragen_von = models.CharField("Eingetragen von", max_length=150, blank=True)
    eingetragen_am = models.DateTimeField("Eingetragen am", auto_now_add=True)
    bedankt_am = models.DateField(
        "Dankesbrief am", null=True, blank=True, editable=False,
        help_text="Wird beim Erstellen der Dankesbriefe gesetzt (ADR 0056).",
    )  # fmt: skip

    class Meta:
        verbose_name = "Spende"
        verbose_name_plural = "Spenden"
        ordering = ["-datum", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["belegnummer"], condition=~models.Q(belegnummer=""),
                                    name="spende_belegnummer_eindeutig"),
        ]  # fmt: skip

    def __str__(self):
        return f"{self.get_art_display()} vom {self.datum:%d.%m.%Y}"

    def clean(self):
        if self.art == self.Art.GELD and not self.betrag:
            raise ValidationError({"betrag": "Bei einer Geldspende bitte den Betrag angeben."})
        if self.betrag is not None and self.betrag < 0:
            raise ValidationError({"betrag": "Der Betrag darf nicht negativ sein."})
        if self.art == self.Art.SACH and not self.beschreibung:
            raise ValidationError({"beschreibung": "Bitte angeben, was gespendet wurde."})

    @property
    def bestaetigt(self) -> bool:
        """Gültig bestätigt; eine stornierte Bestätigung zählt nicht."""
        return self.bestaetigung_id is not None and self.bestaetigung.storniert_am is None


class SpendenBeleg(models.Model):
    """Beleg aus einem anderen Programm, z. B. eine Zuwendungsbestätigung aus dem Vereinsportal
    (ADR 0056). Verschlüsselt über ``apps.core.privatdateien``; liegt dem Dankesbrief bei."""

    ORDNER = "spendenbelege"
    PRIVATDATEI = (ORDNER, "datei")  # Papierkorb (ADR 0073)

    adresse = models.ForeignKey(Adresse, on_delete=models.CASCADE, related_name="spendenbelege",
                                null=True, blank=True, verbose_name="Spender")  # fmt: skip
    spende = models.ForeignKey(Spende, on_delete=models.SET_NULL, related_name="belege",
                               null=True, blank=True)  # fmt: skip
    jahr = models.PositiveIntegerField("Jahr")
    dateiname = models.CharField("Dateiname", max_length=200)
    datei = models.CharField(max_length=100, editable=False)
    hochgeladen_am = models.DateTimeField("Hochgeladen am", auto_now_add=True)
    hochgeladen_von = models.CharField("Hochgeladen von", max_length=150, blank=True)
    beigelegt_am = models.DateField("Beigelegt am", null=True, blank=True)

    class Meta:
        verbose_name = "Spendenbeleg"
        verbose_name_plural = "Spendenbelege"
        ordering = ["-hochgeladen_am"]

    def __str__(self):
        return self.dateiname


def naechste_nummer() -> int:
    """Fortlaufende Bestätigungsnummer; nie doppelt (Zeile gesperrt)."""
    with transaction.atomic():
        e = SpendenEinstellungen.laden()
        e = SpendenEinstellungen.objects.select_for_update().get(pk=e.pk)
        hoechste = Zuwendungsbestaetigung.objects.aggregate(m=models.Max("nummer"))["m"] or 0
        nummer = max(e.naechste_nummer, hoechste + 1)
        e.naechste_nummer = nummer + 1
        e.save(update_fields=["naechste_nummer"])
        return nummer


def summe(spenden) -> Decimal:
    return spenden.aggregate(s=models.Sum("betrag"))["s"] or Decimal("0")


auditlog.register(Spende)
auditlog.register(Zuwendungsbestaetigung)
auditlog.register(SpendenEinstellungen)
auditlog.register(SpendenBeleg, exclude_fields=["datei"])
