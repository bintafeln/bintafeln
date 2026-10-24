from auditlog.registry import auditlog
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice


class Benutzer(AbstractUser):
    """Eigenes Benutzermodell, damit spätere Erweiterungen ohne Umbau möglich sind.

    Mitarbeitende werden nie gelöscht, nur gesperrt (``is_active``), damit auch Jahre später
    nachvollziehbar bleibt, wer wann dabei war und was eingetragen hat (ADR 0015).
    """

    class Beschaeftigung(models.TextChoices):
        EHRENAMTLICH = "ehrenamtlich", "ehrenamtlich"
        FEST = "fest", "fest angestellt"

    beschaeftigung = models.CharField(
        "Beschäftigung",
        max_length=12,
        choices=Beschaeftigung.choices,
        default=Beschaeftigung.EHRENAMTLICH,
    )
    passwort_aendern = models.BooleanField(
        "Muss das Passwort bei der nächsten Anmeldung ändern", default=False
    )
    gesperrt_am = models.DateTimeField("Gesperrt am", null=True, blank=True)
    gesperrt_von = models.CharField("Gesperrt von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"

    def __str__(self):
        return self.get_full_name() or self.username


class Stammdaten(models.Model):
    """Persönliche Angaben einer Mitarbeiterin oder eines Mitarbeiters (ADR 0017).

    Getrennt vom Konto, damit die Löschfrist nach dem Austritt sie leeren kann, während das
    Konto im Archiv nachvollziehbar bleibt.
    """

    benutzer = models.OneToOneField(
        Benutzer, on_delete=models.CASCADE, primary_key=True, related_name="stammdaten"
    )
    anrede = models.CharField("Anrede", max_length=30, blank=True)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    handy = models.CharField("Handy", max_length=50, blank=True)
    notfall_name = models.CharField("Notfallkontakt: Name", max_length=150, blank=True)
    notfall_telefon = models.CharField("Notfallkontakt: Telefon", max_length=50, blank=True)
    eintritt = models.DateField("Eintritt", null=True, blank=True)
    austritt = models.DateField("Austritt", null=True, blank=True)
    bemerkung = models.TextField("Bemerkung", blank=True)
    fs_klassen = models.CharField(
        "Führerscheinklassen", max_length=50, blank=True, help_text="z. B. B, BE, C1"
    )
    fs_gueltig_bis = models.DateField("Führerschein gültig bis", null=True, blank=True)
    fs_gesehen_am = models.DateField("Führerschein zuletzt gesehen am", null=True, blank=True)
    fs_gesehen_von = models.CharField("gesehen von", max_length=150, blank=True)
    ifsg_erstbelehrung_am = models.DateField("Erstbelehrung IfSG (§ 43) am", null=True, blank=True)
    ifsg_belehrung_am = models.DateField("Letzte Folgebelehrung IfSG am", null=True, blank=True)
    # Verschlüsselt unter MEDIA_ROOT/privat/; nur wenn die Tafel Kopien erlaubt (ADR 0017).
    fs_kopie_datei = models.CharField(max_length=200, blank=True, editable=False)
    fs_kopie_typ = models.CharField(max_length=100, blank=True, editable=False)
    fs_kopie_am = models.DateTimeField("Kopie hochgeladen am", null=True, blank=True)
    geleert_am = models.DateTimeField("Nach Löschfrist geleert am", null=True, blank=True)

    class Meta:
        verbose_name = "Stammdaten Mitarbeitende"
        verbose_name_plural = "Stammdaten Mitarbeitende"

    def __str__(self):
        return f"Stammdaten {self.benutzer}"

    @property
    def letzte_ifsg_belehrung(self):
        daten = [d for d in (self.ifsg_erstbelehrung_am, self.ifsg_belehrung_am) if d]
        return max(daten) if daten else None


class PersonalEinstellungen(models.Model):
    """Fristen rund um Mitarbeitende (Singleton)."""

    EINZIGE_ID = 1

    fs_pruefung_monate = models.PositiveSmallIntegerField(
        "Führerschein erneut ansehen nach … Monaten",
        default=6,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
    )
    ifsg_wiederholung_monate = models.PositiveSmallIntegerField(
        "IfSG-Folgebelehrung alle … Monate",
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    vorlauf_tage = models.PositiveSmallIntegerField(
        "Wiedervorlage … Tage vorher anzeigen",
        default=14,
        validators=[MaxValueValidator(90)],
    )
    fs_kopie_erlaubt = models.BooleanField(
        "Kopie des Führerscheins speichern erlauben",
        default=False,
        help_text="In der Regel genügt der Vermerk „gesehen am / von“. Kopien werden "
        "verschlüsselt gespeichert, jeder Abruf wird protokolliert.",
    )
    stammdaten_loeschen_jahre = models.PositiveSmallIntegerField(
        "Stammdaten … Jahre nach Austritt bzw. Sperre leeren",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Name, Rollen und Zeiträume bleiben im Archiv; Anschrift, Telefon, "
        "Notfallkontakt, Führerschein und Belehrungen werden geleert.",
    )

    class Meta:
        verbose_name = "Einstellungen Personal"
        verbose_name_plural = "Einstellungen Personal"

    def __str__(self):
        return "Einstellungen Personal"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "PersonalEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


auditlog.register(Benutzer, exclude_fields=["password", "last_login"], m2m_fields={"groups"})


class Schulung(models.Model):
    benutzer = models.ForeignKey(Benutzer, on_delete=models.CASCADE, related_name="schulungen")
    thema = models.CharField("Thema", max_length=200)
    datum = models.DateField("Datum")
    gueltig_bis = models.DateField(
        "Gültig bis", null=True, blank=True, help_text="Leer = ohne Ablauf."
    )
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Schulung"
        verbose_name_plural = "Schulungen"
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.thema} am {self.datum:%d.%m.%Y}"


auditlog.register(Stammdaten, exclude_fields=["fs_kopie_datei"])
auditlog.register(Schulung)
auditlog.register(PersonalEinstellungen)

# Nur, wer wann ein Gerät eingerichtet oder entfernt hat – nie Schlüssel oder Codes.
auditlog.register(TOTPDevice, include_fields=["user", "name", "confirmed"])
auditlog.register(StaticDevice, include_fields=["user", "name", "confirmed"])
