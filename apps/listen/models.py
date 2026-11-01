from auditlog.registry import auditlog
from django.conf import settings
from django.db import models
from django.utils import timezone


class EigeneListe(models.Model):
    """Eine Liste aus dem Katalog mit eigenen Filtern, Spalten und Sortierung (ADR 0063).
    ``parameter`` ist die Adresszeile der Liste (nur Einstellungen, keine Personendaten)."""

    class Sichtbarkeit(models.TextChoices):
        PRIVAT = "privat", "Nur ich"
        STELLE = "stelle", "Eine Ausgabestelle"
        ALLE_STELLEN = "alle_stellen", "Alle Ausgabestellen"
        PERSON = "person", "Bestimmte Person"
        ALLE = "alle", "Alle"

    titel = models.CharField("Titel", max_length=100)
    kennung = models.CharField("Liste", max_length=40)
    parameter = models.TextField("Einstellungen", blank=True)
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")  # fmt: skip
    sichtbarkeit = models.CharField("Sichtbar für", max_length=12,
                                    choices=Sichtbarkeit.choices,
                                    default=Sichtbarkeit.PRIVAT)  # fmt: skip
    ausgabestelle = models.ForeignKey("kunden.Ausgabestelle", null=True, blank=True,
                                      on_delete=models.CASCADE, related_name="+",
                                      verbose_name="Ausgabestelle")  # fmt: skip
    fuer_person = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.CASCADE, related_name="+",
                                    verbose_name="Person")  # fmt: skip
    erstellt_am = models.DateTimeField("Erstellt am", default=timezone.now)

    class Meta:
        verbose_name = "Eigene Liste"
        verbose_name_plural = "Eigene Listen"
        ordering = ["titel"]

    def __str__(self):
        return self.titel

    def sichtbar_fuer(self, benutzer, meine_stellen) -> bool:
        """Ob die Liste für ``benutzer`` sichtbar ist. ``meine_stellen`` = Menge der
        Ausgabestellen-IDs des Benutzers (einmal berechnet, für viele Listen wiederverwendbar)."""
        if self.benutzer_id == benutzer.pk:
            return True  # die eigene Liste sieht man immer
        if self.sichtbarkeit == self.Sichtbarkeit.ALLE:
            return True
        if self.sichtbarkeit == self.Sichtbarkeit.ALLE_STELLEN:
            return bool(meine_stellen)
        if self.sichtbarkeit == self.Sichtbarkeit.STELLE:
            return self.ausgabestelle_id in meine_stellen
        if self.sichtbarkeit == self.Sichtbarkeit.PERSON:
            return self.fuer_person_id == benutzer.pk
        return False  # privat, fremde Liste


auditlog.register(EigeneListe)
