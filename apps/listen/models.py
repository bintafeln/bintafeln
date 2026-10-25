from auditlog.registry import auditlog
from django.conf import settings
from django.db import models
from django.utils import timezone


class EigeneListe(models.Model):
    """Eine Liste aus dem Katalog mit eigenen Filtern, Spalten und Sortierung (ADR 0063).
    ``parameter`` ist die Adresszeile der Liste (nur Einstellungen, keine Personendaten)."""

    titel = models.CharField("Titel", max_length=100)
    kennung = models.CharField("Liste", max_length=40)
    parameter = models.TextField("Einstellungen", blank=True)
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")  # fmt: skip
    fuer_alle = models.BooleanField("Für alle sichtbar", default=False)
    erstellt_am = models.DateTimeField("Erstellt am", default=timezone.now)

    class Meta:
        verbose_name = "Eigene Liste"
        verbose_name_plural = "Eigene Listen"
        ordering = ["titel"]

    def __str__(self):
        return self.titel


auditlog.register(EigeneListe)
