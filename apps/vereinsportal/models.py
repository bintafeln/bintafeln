"""Spendenbelege aus dem Vereinsportal (ADR 0126).

Die Belege bleiben Belege des Vereinsportals: Sie werden hier nur eingelesen, ausgewertet und
(für Mehrfachspender) weitergegeben. Mit den Spenden und Zuwendungsbestätigungen aus bintafeln
(``apps.spenden``) haben sie bewusst nichts zu tun, damit nie zwei Bestätigungen für dieselbe
Spende entstehen.
"""

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
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
    aufbewahrung_jahre = models.PositiveSmallIntegerField(
        "Aufbewahrung (Jahre)", default=2,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Eingelesene Belege werden nach so vielen vollen Kalenderjahren gelöscht "
        "(gezählt ab Ende des Jahres der Spende). Die Originale bleiben im Vereinsportal.",
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


class Beleg(models.Model):
    """Ein Spendenbeleg (PDF) aus dem Finanzexport, verschlüsselt über ``privatdateien``."""

    ORDNER = "vereinsportal"
    PRIVATDATEI = (ORDNER, "datei")

    dateiname = models.CharField("Dateiname", max_length=200, unique=True)
    belegnummer = models.CharField("Belegnummer", max_length=30, blank=True, db_index=True)
    name = models.CharField("Spender", max_length=250)
    such_name = models.CharField(max_length=250, db_index=True, editable=False)
    strasse = models.CharField("Straße und Hausnummer", max_length=200)
    plz_ort = models.CharField("PLZ und Ort", max_length=200)
    jahr = models.PositiveIntegerField("Jahr", db_index=True)
    betrag = models.DecimalField("Betrag", max_digits=12, decimal_places=2, default=0)
    im_portal_versendet = models.BooleanField(
        "Im Vereinsportal versendet", default=False,
        help_text="Laut Finanzexport ist die Bescheinigung dort schon versendet oder erstellt.",
    )  # fmt: skip
    bedankt_am = models.DateField(
        "Dankesbrief am", null=True, blank=True, editable=False,
        help_text="Wird beim Erstellen oder Senden des Dankesbriefs gesetzt.",
    )  # fmt: skip
    bedankt_per = models.CharField("Dankesbrief per", max_length=10, blank=True, editable=False)
    datei = models.CharField(max_length=100, editable=False)
    eingelesen_am = models.DateTimeField("Eingelesen am", auto_now_add=True)
    eingelesen_von = models.CharField("Eingelesen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Spendenbeleg aus dem Vereinsportal"
        verbose_name_plural = "Spendenbelege aus dem Vereinsportal"
        ordering = ["name", "dateiname"]

    def __str__(self):
        return self.dateiname


class Sammelbescheinigung(models.Model):
    """Im Vereinsportal erstellte Sammelbescheinigung eines Mehrfachspenders (PDF), hochgeladen
    und über den Namen zugeordnet. Sie liegt dem Dankesbrief bei."""

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
auditlog.register(Beleg, exclude_fields=["datei"])
auditlog.register(Sammelbescheinigung, exclude_fields=["datei"])
