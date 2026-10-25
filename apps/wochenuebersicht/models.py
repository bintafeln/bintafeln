from auditlog.registry import auditlog
from django.db import models

from apps.kunden.models import Ausgabestelle


class Selbstabholer(models.Model):
    """Einrichtung, die an festen Tagen selbst abholt (ADR 0054). Zählt nur zu „alle Personen“."""

    name = models.CharField("Name", max_length=150, help_text="Z. B. die Einrichtung.")
    tage = models.CharField("Wochentage", max_length=30, blank=True)
    personen = models.PositiveIntegerField(
        "Personen", default=0, help_text="Wie viele Personen damit versorgt werden."
    )
    aktiv = models.BooleanField("Aktiv", default=True)
    notiz = models.TextField("Notiz", blank=True)

    class Meta:
        verbose_name = "Selbstabholer"
        verbose_name_plural = "Selbstabholer"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def tage_liste(self) -> list[str]:
        return [t.strip() for t in self.tage.split(",") if t.strip()]


class StellenReihenfolge(models.Model):
    """Reihenfolge der Ausgabestellen in der Wochenübersicht (sonst nach Name)."""

    ausgabestelle = models.OneToOneField(Ausgabestelle, on_delete=models.CASCADE, related_name="+")
    reihenfolge = models.PositiveIntegerField("Reihenfolge", default=100)

    class Meta:
        verbose_name = "Reihenfolge der Ausgabestelle"
        verbose_name_plural = "Reihenfolge der Ausgabestellen"

    def __str__(self):
        return f"{self.ausgabestelle} ({self.reihenfolge})"


auditlog.register(Selbstabholer)
