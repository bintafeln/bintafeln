"""Ausgabe (Modul 4): Einstellungen für Empfang und Ampel. Fachliche Grundlage:
docs/fachkonzept.md, Entscheidung: docs/adr/0013-empfang-erfasst-abholungen.md."""

from decimal import Decimal

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def _betrag(name):
    return models.DecimalField(
        name,
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )


class AusgabeEinstellungen(models.Model):
    """Einstellungen der Ausgabe je Tafel (Singleton)."""

    EINZIGE_ID = 1

    class Zeitraum(models.TextChoices):
        WOCHE = "woche", "Kalenderwoche (Montag bis Sonntag)"
        VIERZEHN_TAGE = "14_tage", "14 Tage (heute und die 13 Tage davor)"
        MONAT = "monat", "Kalendermonat"

    max_abholungen = models.PositiveSmallIntegerField(
        "Höchstens … Abholungen",
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    zeitraum = models.CharField(
        "je Zeitraum", max_length=10, choices=Zeitraum.choices, default=Zeitraum.WOCHE
    )
    nicht_dran_rot = models.BooleanField(
        "„Heute nicht dran“ verhindert die Abholung",
        default=True,
        help_text="Ein: rot (nur mit Ausnahme). Aus: gelb, nur ein Hinweis.",
    )
    vorwarnung_tage = models.PositiveSmallIntegerField(
        "Vorwarnung vor Ablauf des Ausweises (Tage)",
        default=14,
        validators=[MaxValueValidator(365)],
    )
    beitrag_je_abholung = _betrag("Beitrag je Abholung (Euro)")
    beitrag_je_erwachsenem = _betrag("zusätzlich je Erwachsenem (Euro)")
    beitrag_je_kind = _betrag("zusätzlich je Kind (Euro)")
    kontostand_anzeigen = models.BooleanField("Kontostand am Empfang anzeigen", default=True)

    class Meta:
        verbose_name = "Einstellungen Ausgabe"
        verbose_name_plural = "Einstellungen Ausgabe"

    def __str__(self):
        return "Einstellungen Ausgabe"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "AusgabeEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    def beitrag(self, erwachsene: int, kinder: int) -> Decimal:
        return (
            self.beitrag_je_abholung
            + erwachsene * self.beitrag_je_erwachsenem
            + kinder * self.beitrag_je_kind
        )


auditlog.register(AusgabeEinstellungen)
