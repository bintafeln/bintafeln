from auditlog.registry import auditlog
from django.contrib.auth.models import AbstractUser
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice


class Benutzer(AbstractUser):
    """Eigenes Benutzermodell, damit spätere Erweiterungen ohne Umbau möglich sind."""

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"

    def __str__(self):
        return self.get_full_name() or self.username


auditlog.register(Benutzer, exclude_fields=["password", "last_login"], m2m_fields={"groups"})

# Nur, wer wann ein Gerät eingerichtet oder entfernt hat – nie Schlüssel oder Codes.
auditlog.register(TOTPDevice, include_fields=["user", "name", "confirmed"])
auditlog.register(StaticDevice, include_fields=["user", "name", "confirmed"])
