from auditlog.registry import auditlog
from django.db import models
from django.utils import timezone

from apps.kunden.models import Ausgabestelle


class Selbstabholer(models.Model):
    """Einrichtung, die an festen Tagen selbst abholt (ADR 0054). Zählt nur zu „alle Personen“."""

    name = models.CharField("Name der Einrichtung", max_length=150,
                            help_text="Z. B. „Frauenhaus Musterstadt“.")  # fmt: skip
    tage = models.CharField("Wochentage", max_length=30, blank=True)
    personen = models.PositiveIntegerField(
        "Personen", default=0, help_text="Wie viele Personen damit versorgt werden."
    )
    aktiv = models.BooleanField("Aktiv", default=True)
    strasse = models.CharField("Straße und Hausnummer", max_length=150, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon der Einrichtung", max_length=50, blank=True)
    email = models.EmailField("E-Mail der Einrichtung", blank=True)
    notiz = models.TextField(
        "Hinweise", blank=True, help_text="Dauerhafte Hinweise, z. B. Abholzeit oder Zufahrt."
    )

    class Meta:
        verbose_name = "Selbstabholer"
        verbose_name_plural = "Selbstabholer"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def tage_liste(self) -> list[str]:
        return [t.strip() for t in self.tage.split(",") if t.strip()]


class SelbstabholerKontakt(models.Model):
    """Ansprechperson eines Selbstabholers; beliebig viele."""

    selbstabholer = models.ForeignKey(Selbstabholer, on_delete=models.CASCADE,
                                      related_name="kontakte")  # fmt: skip
    name = models.CharField("Name", max_length=150)
    funktion = models.CharField("Funktion", max_length=100, blank=True,
                                help_text="z. B. Leitung, Fahrer")  # fmt: skip
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)

    class Meta:
        verbose_name = "Ansprechperson eines Selbstabholers"
        verbose_name_plural = "Ansprechpersonen der Selbstabholer"
        ordering = ["pk"]

    def __str__(self):
        return f"{self.name} ({self.selbstabholer})"


class SelbstabholerNotiz(models.Model):
    """Gesprächsnotiz: was mit dem Selbstabholer besprochen wurde, mit Datum und Verfasser."""

    selbstabholer = models.ForeignKey(Selbstabholer, on_delete=models.CASCADE,
                                      related_name="notizen")  # fmt: skip
    text = models.TextField("Notiz")
    erstellt_am = models.DateTimeField("Erstellt am", default=timezone.now)
    verfasst_von = models.CharField("Verfasst von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Notiz zu einem Selbstabholer"
        verbose_name_plural = "Notizen zu Selbstabholern"
        ordering = ["-erstellt_am", "-pk"]

    def __str__(self):
        return f"Notiz vom {timezone.localtime(self.erstellt_am):%d.%m.%Y} ({self.selbstabholer})"


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
auditlog.register(SelbstabholerKontakt)
auditlog.register(SelbstabholerNotiz)
