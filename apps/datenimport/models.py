import datetime as dt
import uuid

from auditlog.registry import auditlog
from django.conf import settings
from django.db import models
from django.utils import timezone


class ImportSitzung(models.Model):
    """Hochgeladene Tabellen, Zuordnung und Abgleich bis zur Übernahme (ADR 0078).

    Enthält vorübergehend Inhalte der Dateien und wird deshalb spätestens nach zwei Stunden
    gelöscht; nicht in der Datensicherung."""

    GUELTIG = dt.timedelta(hours=2)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    erstellt_am = models.DateTimeField(default=timezone.now)
    ziel = models.CharField(max_length=30)
    dateien = models.JSONField(default=list)
    tabellen = models.JSONField(default=list)  # [{name, zeilen, hinweise, kopf, art, zuordnung}]
    saetze = models.JSONField(default=list)
    meldungen = models.JSONField(default=list)
    plan = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Importsitzung"
        verbose_name_plural = "Importsitzungen"

    def __str__(self):
        return f"Import {self.ziel} vom {timezone.localtime(self.erstellt_am):%d.%m.%Y %H:%M}"

    @classmethod
    def abgelaufene_loeschen(cls) -> int:
        return cls.objects.filter(erstellt_am__lt=timezone.now() - cls.GUELTIG).delete()[0]


class ImportVorlage(models.Model):
    """Gespeicherte Spaltenzuordnung, z. B. für den Export eines bestimmten Altprogramms."""

    ziel = models.CharField(max_length=30)
    art = models.CharField(max_length=30)
    name = models.CharField("Name", max_length=100)
    zuordnung = models.JSONField(default=dict)  # normalisierte Überschrift → Feld
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Importvorlage"
        verbose_name_plural = "Importvorlagen"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["ziel", "art", "name"], name="importvorlage_eindeutig")
        ]

    def __str__(self):
        return self.name

    def passt(self, kopf_normal: list[str]) -> int:
        """Wie viele Überschriften die Vorlage kennt."""
        return sum(1 for k in kopf_normal if k and k in self.zuordnung)


auditlog.register(ImportVorlage)
