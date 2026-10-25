"""Mitglieder des Trägervereins (Modul 5, ADR 0046).

Ein Mitglied ist eine Adresse aus dem Adressbuch mit Mitgliedschaft. Beitragszahlungen sind
Spenden mit dem Häkchen „Mitgliedsbeitrag“ (ADR 0045): So erscheinen sie in den Spenden, in
der Auskunft und lassen sich mit Zuwendungsbestätigungen bestätigen, ohne doppelte Erfassung.
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from auditlog.registry import auditlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.adressen.models import Adresse


class MitgliederEinstellungen(models.Model):
    EINZIGE_ID = 1
    naechste_nummer = models.PositiveIntegerField("Nächste Mitgliedsnummer", default=1)
    beitraege = models.BooleanField(
        "Mitglieder zahlen Beiträge",
        default=False,
        help_text="Aus: Jahresbeitrag, Soll, offene Beiträge und das Häkchen „Mitgliedsbeitrag“ "
        "bei Spenden werden nirgends angezeigt.",
    )
    standard_beitrag = models.DecimalField(
        "Jahresbeitrag (Vorgabe für neue Mitglieder)", max_digits=8, decimal_places=2,
        default=Decimal("0"),
    )  # fmt: skip
    anteilig = models.BooleanField(
        "Beitrag im Ein- und Austrittsjahr anteilig",
        default=False,
        help_text="An: nur die Monate der Mitgliedschaft zählen. Aus: voller Jahresbeitrag.",
    )

    class Meta:
        verbose_name = "Einstellungen für Mitglieder"
        verbose_name_plural = "Einstellungen für Mitglieder"

    def __str__(self):
        return "Einstellungen für Mitglieder"

    @classmethod
    def laden(cls):
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    @classmethod
    def mit_beitraegen(cls) -> bool:
        return cls.laden().beitraege


class Mitglied(models.Model):
    adresse = models.OneToOneField(Adresse, on_delete=models.PROTECT, related_name="mitglied")
    nummer = models.CharField("Mitgliedsnummer", max_length=20, unique=True)
    art = models.CharField("Art der Mitgliedschaft", max_length=50)
    eintritt = models.DateField("Eintritt")
    austritt = models.DateField("Austritt", null=True, blank=True)
    austrittsgrund = models.CharField("Grund des Austritts", max_length=50, blank=True)
    jahresbeitrag = models.DecimalField("Jahresbeitrag (Euro)", max_digits=8, decimal_places=2,
                                        default=Decimal("0"))  # fmt: skip
    zahlweise = models.CharField("Zahlweise", max_length=30, blank=True)
    zahlungsart = models.CharField("Zahlungsart", max_length=30, blank=True)
    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="mitglied", verbose_name="Zugleich Mitarbeiter/in (Konto)",
    )  # fmt: skip
    notiz = models.TextField("Notiz", blank=True)
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        verbose_name = "Mitglied"
        verbose_name_plural = "Mitglieder"
        ordering = ["nummer"]

    def __str__(self):
        return f"{self.nummer} · {self.adresse.name}"

    def clean(self):
        if self.austritt and self.eintritt and self.austritt < self.eintritt:
            raise ValidationError({"austritt": "Der Austritt liegt vor dem Eintritt."})
        if self.jahresbeitrag is not None and self.jahresbeitrag < 0:
            raise ValidationError({"jahresbeitrag": "Der Beitrag darf nicht negativ sein."})

    def ist_mitglied(self, tag: dt.date) -> bool:
        return self.eintritt <= tag and (self.austritt is None or tag <= self.austritt)

    def monate(self, jahr: int) -> int:
        """Angefangene Monate der Mitgliedschaft im Jahr (Eintritts- und Austrittsmonat zählen)."""
        anfang = max(self.eintritt, dt.date(jahr, 1, 1))
        ende = min(self.austritt or dt.date(jahr, 12, 31), dt.date(jahr, 12, 31))
        if ende < anfang:
            return 0
        return (ende.year - anfang.year) * 12 + ende.month - anfang.month + 1

    def soll(self, jahr: int, anteilig: bool) -> Decimal:
        monate = self.monate(jahr)
        if not monate:
            return Decimal("0")
        if not anteilig:
            return self.jahresbeitrag
        return (self.jahresbeitrag * monate / 12).quantize(Decimal("0.01"), ROUND_HALF_UP)

    def gezahlt(self, jahr: int) -> Decimal:
        from apps.spenden.models import Spende

        return self.adresse.spenden.filter(
            art=Spende.Art.GELD, mitgliedsbeitrag=True, datum__year=jahr
        ).aggregate(s=models.Sum("betrag"))["s"] or Decimal("0")


def naechste_nummer() -> str:
    """Nächste freie Mitgliedsnummer (Zeile gesperrt, damit nie doppelt)."""
    with transaction.atomic():
        e = MitgliederEinstellungen.laden()
        e = MitgliederEinstellungen.objects.select_for_update().get(pk=e.pk)
        nummer = e.naechste_nummer
        while Mitglied.objects.filter(nummer=str(nummer)).exists():
            nummer += 1
        e.naechste_nummer = nummer + 1
        e.save(update_fields=["naechste_nummer"])
        return str(nummer)


def nummer_verbraucht(nummer: str) -> None:
    """Nach dem Speichern: Der Vorschlag für die nächste Nummer liegt hinter dieser."""
    if nummer.isdigit():
        MitgliederEinstellungen.laden()
        MitgliederEinstellungen.objects.filter(naechste_nummer__lte=int(nummer)).update(
            naechste_nummer=int(nummer) + 1
        )


auditlog.register(Mitglied, exclude_fields=["geaendert_am"])
auditlog.register(MitgliederEinstellungen)
