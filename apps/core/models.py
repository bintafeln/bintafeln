from auditlog.registry import auditlog
from django.db import models


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
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    zwei_faktor_admin = models.BooleanField("Zwei-Faktor Pflicht für Admin", default=True)
    zwei_faktor_buero = models.BooleanField("Zwei-Faktor Pflicht für Büro", default=True)
    zwei_faktor_ausgabe = models.BooleanField("Zwei-Faktor Pflicht für Ausgabe", default=False)
    zwei_faktor_kiosk = models.BooleanField("Zwei-Faktor Pflicht für Kiosk", default=False)
    zwei_faktor_fahrer = models.BooleanField("Zwei-Faktor Pflicht für Fahrer", default=False)
    zwei_faktor_beifahrer = models.BooleanField("Zwei-Faktor Pflicht für Beifahrer", default=False)
    buero_verwaltet_mitarbeitende = models.BooleanField(
        "Büro darf Mitarbeitende verwalten",
        default=False,
        help_text="Anlegen, bearbeiten und sperren – aber keine Admin-Konten und keine "
        "Admin-Rolle vergeben.",
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

    def zwei_faktor_pflicht_rollen(self) -> set[str]:
        from apps.konten import rollen

        felder = {
            rollen.ADMIN: self.zwei_faktor_admin,
            rollen.BUERO: self.zwei_faktor_buero,
            rollen.AUSGABE: self.zwei_faktor_ausgabe,
            rollen.KIOSK: self.zwei_faktor_kiosk,
            rollen.FAHRER: self.zwei_faktor_fahrer,
            rollen.BEIFAHRER: self.zwei_faktor_beifahrer,
        }
        return {rolle for rolle, pflicht in felder.items() if pflicht}

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
