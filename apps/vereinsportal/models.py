"""Einstellungen und Hilfslisten für das Einlesen aus dem Vereinsportal (ADR 0126, 0128).

Die Spenden selbst liegen im gemeinsamen Spendenpool (``apps.spenden``); hier stehen nur die
Einstellungen und die Liste „Spender mit E-Mail“, aus der beim Einlesen E-Mail und Versandweg
ins Adressbuch kommen.
"""

from auditlog.registry import auditlog
from django.db import models


class PortalEinstellungen(models.Model):
    """Einstellungen des Moduls (Singleton)."""

    EINZIGE_ID = 1

    absender = models.CharField(
        "Name des Vereins im Absender der Belege", max_length=200, blank=True,
        help_text="So, wie er auf den Spendenbelegen in der Absenderzeile über der Anschrift "
        "steht (z. B. „Tafel Musterstadt e.V.“). Die Zeile darunter liest bintafeln als Spender. "
        "Leer: die erste Zeile mit „|“ gilt als Absenderzeile.",
    )  # fmt: skip
    # Automatischer Abruf über den Dienst „abruf“ (ADR 0127)
    anmeldung_url = models.URLField(
        "Adresse der Anmeldeseite", blank=True,
        help_text="Die Adresse, unter der Sie sich im Vereinsportal anmelden (https://…).",
    )  # fmt: skip
    liste_url = models.URLField(
        "Adresse der Liste „Spender mit E-Mail“", blank=True, max_length=500,
        help_text="Die Liste im Vereinsportal öffnen und die Adresse aus der Adresszeile des "
        "Browsers hierher kopieren. Leer: Die Liste wird nicht abgerufen.",
    )  # fmt: skip
    export_url = models.URLField(
        "Adresse der Seite „Finanzexport“", blank=True, max_length=500,
        help_text="Die Seite mit dem Export für den Steuerberater öffnen und die Adresse aus "
        "der Adresszeile hierher kopieren.",
    )  # fmt: skip
    email = models.EmailField("E-Mail für die Anmeldung im Vereinsportal", blank=True)
    passwort_verschluesselt = models.TextField(blank=True, editable=False)

    class Meta:
        verbose_name = "Einstellungen für das Vereinsportal"
        verbose_name_plural = "Einstellungen für das Vereinsportal"

    def __str__(self):
        return "Einstellungen für das Vereinsportal"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls):
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    @property
    def abruf_eingerichtet(self) -> bool:
        return bool(self.anmeldung_url and self.export_url and self.email
                    and self.passwort_verschluesselt)  # fmt: skip


class Kontakt(models.Model):
    """Zeile der Liste „Spender mit E-Mail“ aus dem Vereinsportal. Jedes Einlesen ersetzt die
    Liste vollständig."""

    such_name = models.CharField(max_length=250, unique=True, editable=False)
    vorname = models.CharField("Vorname", max_length=120, blank=True)
    nachname = models.CharField("Nachname", max_length=120, blank=True)
    anrede = models.CharField("Anrede", max_length=30, blank=True)
    email = models.EmailField("E-Mail")
    immer_post = models.BooleanField("immer per Post", default=False)

    class Meta:
        verbose_name = "Spender mit E-Mail"
        verbose_name_plural = "Spender mit E-Mail"
        ordering = ["nachname", "vorname"]

    def __str__(self):
        return f"{self.vorname} {self.nachname}".strip()


class Sammelbescheinigung(models.Model):
    """Früher hochgeladene Sammelbescheinigung aus dem Vereinsportal. Wird nicht mehr verwendet:
    Für Mehrfachspender stellt bintafeln die Sammelbestätigung jetzt selbst aus (ADR 0128). Die
    Tabelle bleibt, damit beim Update nichts gelöscht wird."""

    ORDNER = "vereinsportal-sammel"
    PRIVATDATEI = (ORDNER, "datei")

    jahr = models.PositiveIntegerField("Jahr")
    name = models.CharField("Spender", max_length=250, blank=True)
    such_name = models.CharField(max_length=250, blank=True, db_index=True, editable=False)
    dateiname = models.CharField("Dateiname", max_length=200)
    datei = models.CharField(max_length=100, editable=False)
    hochgeladen_am = models.DateTimeField("Hochgeladen am", auto_now_add=True)
    hochgeladen_von = models.CharField("Hochgeladen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Sammelbescheinigung"
        verbose_name_plural = "Sammelbescheinigungen"
        ordering = ["name", "dateiname"]

    def __str__(self):
        return self.dateiname


auditlog.register(PortalEinstellungen, exclude_fields=["passwort_verschluesselt"])
auditlog.register(Kontakt)
auditlog.register(Sammelbescheinigung, exclude_fields=["datei"])
