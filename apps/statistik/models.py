"""Einstellungen der Statistik (ADR 0036): welche Diagramme die Tafel sehen möchte.

Tafelweit (nicht je Person): Ein Admin wählt unter „Einstellungen → Statistik", welche der
einzelnen Grafiken auf der Statistik-Seite und im PDF-Jahresbericht erscheinen. Gespeichert wird
die Menge der *ausgeblendeten* Diagramme über ihren Schlüssel (``DIAGRAMME`` in ``views.py``);
unbekannte Schlüssel schaden nicht. Leer = alle sichtbar (Vorgabe).
"""

from django.db import models


class StatistikEinstellungen(models.Model):
    EINZIGE_ID = 1
    ausgeblendet = models.JSONField(
        "Ausgeblendete Diagramme", default=list, blank=True,
        help_text="Schlüssel der Diagramme, die nicht gezeigt werden. Leer = alle.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Einstellungen für die Statistik"
        verbose_name_plural = "Einstellungen für die Statistik"

    def __str__(self):
        return "Einstellungen für die Statistik"

    @classmethod
    def laden(cls) -> "StatistikEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    @classmethod
    def versteckt(cls) -> set[str]:
        return set(cls.laden().ausgeblendet or [])
