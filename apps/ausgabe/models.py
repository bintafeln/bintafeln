"""Ausgabe (Modul 4): Einstellungen für Empfang und Ampel. Fachliche Grundlage:
docs/fachkonzept.md, Entscheidung: docs/adr/0013-empfang-erfasst-abholungen.md."""

from decimal import Decimal

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.kunden.models import Abholung, Ausgabestelle, Haushalt


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
    anschreiben_erlaubt = models.BooleanField(
        "Anschreiben erlauben",
        default=False,
        help_text="Abholung ohne Zahlung; der Kontostand darf dann negativ werden.",
    )
    buchungen_aufbewahren_jahre = models.PositiveSmallIntegerField(
        "Kontobuchungen aufbewahren (Jahre)",
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Für die Kasse. Nach Ablauf der Frist für Abholungen werden Buchungen "
        "anonymisiert (ohne Kundennummer), nach dieser Frist gelöscht. Bitte mit der "
        "Kassenführung des Vereins abstimmen.",
    )

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


class Buchung(models.Model):
    """Eine Buchung im Kundenkonto. Auswirkung auf den Kontostand: haben − soll.

    ``bar`` ist das dabei bar eingenommene Geld (für die Kasse). Die Buchung hängt zusätzlich an
    der Kundennummer, damit die Kasse einen Neuimport des Kundenstamms übersteht (ADR 0014).
    """

    class Art(models.TextChoices):
        ABHOLUNG = "abholung", "Abholung"
        EINZAHLUNG = "einzahlung", "Einzahlung"
        KORREKTUR = "korrektur", "Korrektur"

    class Zahlweise(models.TextChoices):
        GUTHABEN = "guthaben", "aus Guthaben, Rest bar"
        BAR = "bar", "alles bar"
        ANSCHREIBEN = "anschreiben", "anschreiben"

    haushalt = models.ForeignKey(
        Haushalt, null=True, blank=True, on_delete=models.SET_NULL, related_name="buchungen"
    )
    kundennummer = models.CharField("Kundennummer", max_length=20, blank=True)
    datum = models.DateField("Datum", default=timezone.localdate, db_index=True)
    zeitpunkt = models.DateTimeField("Zeitpunkt", default=timezone.now)
    art = models.CharField("Art", max_length=12, choices=Art.choices)
    zahlweise = models.CharField("Zahlweise", max_length=12, choices=Zahlweise.choices, blank=True)
    soll = models.DecimalField("Soll", max_digits=8, decimal_places=2, default=Decimal("0.00"))
    haben = models.DecimalField("Haben", max_digits=8, decimal_places=2, default=Decimal("0.00"))
    bar = models.DecimalField(
        "Bar eingenommen", max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    abholung = models.OneToOneField(
        Abholung, null=True, blank=True, on_delete=models.SET_NULL, related_name="buchung"
    )
    ausgabestelle = models.ForeignKey(
        Ausgabestelle, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=100, blank=True)

    class Meta:
        verbose_name = "Buchung"
        verbose_name_plural = "Buchungen"
        ordering = ["-zeitpunkt"]

    def __str__(self):
        return f"{self.get_art_display()} vom {self.datum:%d.%m.%Y}"

    @property
    def wirkung(self) -> Decimal:
        """Veränderung des Kontostands."""
        return self.haben - self.soll


auditlog.register(Buchung)
