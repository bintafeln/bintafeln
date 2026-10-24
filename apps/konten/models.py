from auditlog.registry import auditlog
from django.contrib.auth.models import AbstractUser
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


auditlog.register(Benutzer, exclude_fields=["password", "last_login"], m2m_fields={"groups"})

# Nur, wer wann ein Gerät eingerichtet oder entfernt hat – nie Schlüssel oder Codes.
auditlog.register(TOTPDevice, include_fields=["user", "name", "confirmed"])
auditlog.register(StaticDevice, include_fields=["user", "name", "confirmed"])
