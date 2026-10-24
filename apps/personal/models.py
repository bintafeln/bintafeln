"""Personaldaten Festangestellter: Arbeitsvertrag, Abwesenheiten, Stunden (ADR 0018).

Nur für Admin und die Rolle Personal. Krankheit ist eine Gesundheitsangabe (Art. 9 DSGVO):
erfasst werden nur Zeitraum und ob eine Arbeitsunfähigkeitsbescheinigung vorliegt.
"""

from decimal import Decimal

from auditlog.registry import auditlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Ablage der verschlüsselten Vertragsdokumente unter MEDIA_ROOT/privat/ (apps.core.privatdateien).
DOKUMENT_ORDNER = "arbeitsvertrag"


class Arbeitsvertrag(models.Model):
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vertraege"
    )
    beginn = models.DateField("Beginn")
    ende = models.DateField(
        "Ende",
        null=True,
        blank=True,
        help_text="Befristet bis oder gekündigt zum. Leer = unbefristet.",
    )
    taetigkeit = models.CharField("Tätigkeit", max_length=200, blank=True)
    wochenstunden = models.DecimalField(
        "Wochenstunden",
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("60"))],
    )
    urlaubstage = models.DecimalField(
        "Urlaubstage pro Jahr",
        max_digits=4,
        decimal_places=1,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("60"))],
    )
    stundenlohn = models.DecimalField(
        "Stundenlohn (Euro brutto)", max_digits=6, decimal_places=2, null=True, blank=True
    )
    bemerkung = models.TextField("Bemerkung", blank=True)
    dokument_datei = models.CharField(max_length=200, blank=True, editable=False)
    dokument_typ = models.CharField(max_length=100, blank=True, editable=False)

    class Meta:
        verbose_name = "Arbeitsvertrag"
        verbose_name_plural = "Arbeitsverträge"
        ordering = ["-beginn"]

    def __str__(self):
        return f"Arbeitsvertrag ab {self.beginn:%d.%m.%Y}"

    def clean(self):
        if self.ende and self.beginn and self.ende < self.beginn:
            raise ValidationError({"ende": "Das Ende liegt vor dem Beginn."})

    def gilt_am(self, datum) -> bool:
        return self.beginn <= datum and (self.ende is None or datum <= self.ende)

    @property
    def tagessoll(self) -> Decimal:
        """Sollstunden je Werktag (Montag bis Freitag)."""
        return self.wochenstunden / 5


class Abwesenheit(models.Model):
    class Art(models.TextChoices):
        URLAUB = "urlaub", "Urlaub"
        KRANK = "krank", "krank"

    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="abwesenheiten"
    )
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.URLAUB)
    von = models.DateField("Von")
    bis = models.DateField("Bis")
    tage = models.DecimalField(
        "Arbeitstage",
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Leer = Montag bis Freitag im Zeitraum. Feiertage und halbe Tage bitte selbst "
        "eintragen.",
    )
    au_vorgelegt = models.BooleanField("Arbeitsunfähigkeitsbescheinigung liegt vor", default=False)
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Abwesenheit"
        verbose_name_plural = "Abwesenheiten"
        ordering = ["-von"]

    def __str__(self):
        return f"{self.get_art_display()} {self.von:%d.%m.%Y}–{self.bis:%d.%m.%Y}"

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError({"bis": "„Bis“ liegt vor „Von“."})


class Urlaubsjahr(models.Model):
    """Abweichungen für ein Urlaubsjahr; ohne Eintrag gelten die berechneten Werte."""

    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="urlaubsjahre"
    )
    jahr = models.PositiveSmallIntegerField("Jahr")
    anspruch = models.DecimalField(
        "Anspruch (abweichend)", max_digits=4, decimal_places=1, null=True, blank=True
    )
    verfall_am = models.DateField(
        "Resturlaub aus dem Vorjahr verfällt am (abweichend)", null=True, blank=True
    )

    class Meta:
        verbose_name = "Urlaubsjahr"
        verbose_name_plural = "Urlaubsjahre"
        constraints = [
            models.UniqueConstraint(fields=["benutzer", "jahr"], name="ein_urlaubsjahr_je_person")
        ]

    def __str__(self):
        return f"Urlaubsjahr {self.jahr}"


class Stunden(models.Model):
    benutzer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stunden"
    )
    datum = models.DateField("Datum")
    stunden = models.DecimalField(
        "Stunden", max_digits=5, decimal_places=2, help_text="Minus für Korrekturen."
    )
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Stunden"
        verbose_name_plural = "Stunden"
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.stunden} Stunden am {self.datum:%d.%m.%Y}"


auditlog.register(Arbeitsvertrag, exclude_fields=["dokument_datei"])
auditlog.register(Abwesenheit)
auditlog.register(Urlaubsjahr)
auditlog.register(Stunden)
