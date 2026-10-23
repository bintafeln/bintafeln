from auditlog.registry import auditlog
from django.contrib.auth.models import AbstractUser


class Benutzer(AbstractUser):
    """Eigenes Benutzermodell, damit spätere Erweiterungen ohne Umbau möglich sind."""

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"

    def __str__(self):
        return self.get_full_name() or self.username


auditlog.register(Benutzer, exclude_fields=["password", "last_login"], m2m_fields={"groups"})
