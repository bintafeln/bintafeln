from auditlog.registry import auditlog
from django.core.validators import RegexValidator
from django.db import models

from apps.core.farben import STANDARDFARBE, farbtoene
from apps.core.feiertage import BUNDESLAENDER


class TafelEinstellungen(models.Model):
    """Stammdaten der Tafel. Jede Installation gehört zu genau einer Tafel (Singleton)."""

    EINZIGE_ID = 1

    name = models.CharField("Name der Tafel", max_length=200, blank=True)
    logo = models.ImageField(
        "Logo",
        upload_to="oeffentlich/logo/",
        blank=True,
        help_text="PNG, JPG oder WebP, höchstens 2 MB. Das Logo ist öffentlich abrufbar.",
    )
    farbe = models.CharField(
        "Farbe",
        max_length=7,
        default=STANDARDFARBE,
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Bitte eine Farbe wählen.")],
        help_text="Kopfzeile, Knöpfe und Links der ganzen Anwendung und des Antragsformulars. "
        "Voreingestellt ist Tafel-Orange.",
    )
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    bundesland = models.CharField(
        "Bundesland",
        max_length=2,
        choices=BUNDESLAENDER,
        blank=True,
        help_text="Für die gesetzlichen Feiertage (Urlaub, Stundenkonto, Vorauszahlung).",
    )
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        verbose_name = "Tafel-Einstellungen"
        verbose_name_plural = "Tafel-Einstellungen"

    def __str__(self):
        return self.name or "Tafel-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Die Tafel-Einstellungen können nicht gelöscht werden.")

    @classmethod
    def laden(cls) -> "TafelEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    def farben(self) -> dict[str, str]:
        """Aus der einen Farbe abgeleitete Töne für die CSS-Variablen."""
        return farbtoene(self.farbe)

    @property
    def anschrift(self) -> str:
        ort = " ".join(teil for teil in (self.plz, self.ort) if teil)
        return ", ".join(teil for teil in (self.strasse, ort) if teil)


class MailEinstellungen(models.Model):
    """Zugang zum Mailserver der Tafel (Singleton). Das Passwort liegt nur verschlüsselt vor."""

    EINZIGE_ID = 1

    class Verschluesselung(models.TextChoices):
        STARTTLS = "starttls", "STARTTLS (meist Port 587)"
        SSL = "ssl", "SSL/TLS (meist Port 465)"
        KEINE = "keine", "keine (nur im eigenen Netz)"

    server = models.CharField(
        "Mailserver (SMTP)", max_length=200, blank=True, help_text="Leer = keine Mails senden."
    )
    port = models.PositiveIntegerField("Port", default=587)
    verschluesselung = models.CharField(
        "Verschlüsselung",
        max_length=10,
        choices=Verschluesselung.choices,
        default=Verschluesselung.STARTTLS,
    )
    benutzer = models.CharField("Benutzername", max_length=200, blank=True)
    passwort_verschluesselt = models.TextField(blank=True, editable=False)
    absender = models.EmailField(
        "Absenderadresse", blank=True, help_text="Leer = E-Mail der Tafel aus den Einstellungen."
    )

    class Meta:
        verbose_name = "E-Mail-Einstellungen"
        verbose_name_plural = "E-Mail-Einstellungen"

    def __str__(self):
        return "E-Mail-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "MailEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    @property
    def absenderadresse(self) -> str:
        return self.absender or TafelEinstellungen.laden().email

    @property
    def eingerichtet(self) -> bool:
        return bool(self.server and self.absenderadresse)


auditlog.register(TafelEinstellungen, exclude_fields=["geaendert_am"])
# Das (verschlüsselte) Passwort gehört nicht ins Änderungsprotokoll.
auditlog.register(MailEinstellungen, exclude_fields=["passwort_verschluesselt"])
