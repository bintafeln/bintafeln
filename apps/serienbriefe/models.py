"""Serienbriefe (Modul 5, ADR 0047): Vorlagen mit Platzhaltern und vermerkte Versände."""

from auditlog.registry import auditlog
from django.db import models


class Vorlage(models.Model):
    name = models.CharField("Name", max_length=100, unique=True)
    betreff = models.CharField("Betreff", max_length=200)
    text = models.TextField(
        "Text",
        help_text="Absätze durch eine Leerzeile trennen. Platzhalter in geschweiften Klammern, "
        "z. B. {anrede} oder {spendensumme}; die Liste steht unter dem Feld.",
    )
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        verbose_name = "Serienbrief-Vorlage"
        verbose_name_plural = "Serienbrief-Vorlagen"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Versand(models.Model):
    class Art(models.TextChoices):
        BRIEF = "brief", "Briefe (PDF)"
        EMAIL = "email", "E-Mail"

    am = models.DateTimeField("Am", auto_now_add=True)
    von = models.CharField("Von", max_length=150)
    art = models.CharField("Art", max_length=10, choices=Art.choices)
    vorlage = models.CharField("Vorlage", max_length=100)
    betreff = models.CharField("Betreff", max_length=200)
    auswahl = models.CharField("Empfänger", max_length=300)
    anzahl = models.PositiveIntegerField("Anzahl")
    empfaenger = models.JSONField(
        "Empfänger-Schlüssel", default=list,
        help_text="a:<Adresse> bzw. k:<Kundennummer>; für die Auskunft, wer was bekommen hat.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Serienbrief-Versand"
        verbose_name_plural = "Serienbrief-Versände"
        ordering = ["-am"]

    def __str__(self):
        return f"{self.betreff} ({self.am:%d.%m.%Y})"


auditlog.register(Vorlage, exclude_fields=["geaendert_am"])
