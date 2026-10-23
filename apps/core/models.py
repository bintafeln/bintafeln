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

    @property
    def anschrift(self) -> str:
        ort = " ".join(teil for teil in (self.plz, self.ort) if teil)
        return ", ".join(teil for teil in (self.strasse, ort) if teil)


auditlog.register(TafelEinstellungen, exclude_fields=["geaendert_am"])
