"""Monatsabrechnung je Ausgabestelle (ADR 0060).

Einnahmen kommen aus den Kontobuchungen der Ausgabestelle (Kasse, ADR 0014); beim Einreichen
werden sie in ``einnahmen`` festgehalten, weil Buchungen nach ihrer Frist gelöscht werden.
Ausgaben trägt die Ausgabestelle selbst ein, Quittungen liegen verschlüsselt über
``apps.core.privatdateien``.
"""

from decimal import Decimal

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.kunden.models import Ausgabestelle

ARTEN = ["Fahrtkosten", "Verbrauchsmaterial", "Reinigung", "Müll", "Miete und Gebühren",
         "Reparatur", "Anschaffungen", "Sonstiges"]  # fmt: skip


def _arten():
    return list(ARTEN)


class AbrechnungEinstellungen(models.Model):
    """Einstellungen der Abrechnung (Singleton)."""

    EINZIGE_ID = 1

    arten = models.JSONField("Arten der Ausgaben", default=_arten, blank=True)
    aufbewahrung_jahre = models.PositiveSmallIntegerField(
        "Aufbewahrung (Jahre)",
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Abrechnungen und Quittungen werden nach so vielen vollen Kalenderjahren "
        "gelöscht (gezählt ab Ende des Jahres der Abrechnung).",
    )

    class Meta:
        verbose_name = "Abrechnung-Einstellungen"
        verbose_name_plural = "Abrechnung-Einstellungen"

    def __str__(self):
        return "Abrechnung-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "AbrechnungEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


class Monatsabrechnung(models.Model):
    class Status(models.TextChoices):
        OFFEN = "offen", "offen"
        EINGEREICHT = "eingereicht", "eingereicht"
        BESTAETIGT = "bestaetigt", "bestätigt"

    stelle = models.ForeignKey(Ausgabestelle, on_delete=models.PROTECT, related_name="+",
                               verbose_name="Ausgabestelle")  # fmt: skip
    monat = models.DateField("Monat", help_text="Immer der Erste des Monats.")
    status = models.CharField("Status", max_length=12, choices=Status.choices,
                              default=Status.OFFEN)  # fmt: skip
    # Kennzahlen der Kasse beim Einreichen (Beträge als Text), leer solange offen
    einnahmen = models.JSONField("Einnahmen beim Einreichen", default=dict, blank=True)
    anmerkung = models.TextField("Anmerkung", blank=True)
    eingereicht_am = models.DateTimeField("Eingereicht am", null=True, blank=True)
    eingereicht_von = models.CharField("Eingereicht von", max_length=150, blank=True)
    bestaetigt_am = models.DateTimeField("Bestätigt am", null=True, blank=True)
    bestaetigt_von = models.CharField("Bestätigt von", max_length=150, blank=True)
    rueckgabe = models.CharField("Grund der Rückgabe", max_length=300, blank=True)

    class Meta:
        verbose_name = "Monatsabrechnung"
        verbose_name_plural = "Monatsabrechnungen"
        ordering = ["-monat", "stelle__name"]
        constraints = [models.UniqueConstraint(fields=["stelle", "monat"],
                                               name="abrechnung_je_stelle_und_monat")]  # fmt: skip

    def __str__(self):
        return f"{self.stelle} {self.monat:%m/%Y}"

    @property
    def offen(self) -> bool:
        return self.status == self.Status.OFFEN


class Posten(models.Model):
    """Eine Ausgabe der Ausgabestelle, gegebenenfalls mit Quittung."""

    ORDNER = "quittungen"

    abrechnung = models.ForeignKey(Monatsabrechnung, on_delete=models.CASCADE,
                                   related_name="posten")  # fmt: skip
    datum = models.DateField("Datum", default=timezone.localdate)
    betrag = models.DecimalField("Betrag (Euro)", max_digits=9, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])  # fmt: skip
    art = models.CharField("Art", max_length=80)
    empfaenger = models.CharField("Bezahlt an", max_length=150, blank=True,
                                  help_text="z. B. Geschäft, Vermieter, Stadt")  # fmt: skip
    anmerkung = models.CharField("Anmerkung", max_length=300, blank=True)
    quittung = models.CharField(max_length=100, blank=True, editable=False)
    quittung_typ = models.CharField(max_length=40, blank=True, editable=False)
    eingetragen_am = models.DateTimeField("Eingetragen am", auto_now_add=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Ausgabe der Abrechnung"
        verbose_name_plural = "Ausgaben der Abrechnung"
        ordering = ["datum", "pk"]

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.art} {self.betrag}"


auditlog.register(AbrechnungEinstellungen)
auditlog.register(Monatsabrechnung)
auditlog.register(Posten, exclude_fields=["quittung"])
