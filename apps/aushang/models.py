"""Aushang-Monitore (ADR 0080): Seiten der Module (z. B. Dienstplan, Fahrerplan) ganzseitig auf
einem Monitor, ohne Anmeldung, nur über den geheimen Schlüssel im Link."""

import secrets

from auditlog.registry import auditlog
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def neuer_schluessel() -> str:
    return secrets.token_urlsafe(24)


class Aushang(models.Model):
    name = models.CharField(
        "Name", max_length=100, help_text="z. B. „Monitor Ausgabe Mitte“ oder „Monitor Fahrerraum“"
    )
    aktiv = models.BooleanField("Aktiv", default=True,
                                help_text="Aus: Der Link zeigt nichts mehr an.")  # fmt: skip
    schluessel = models.CharField("Schlüssel des Links", max_length=64, unique=True,
                                  default=neuer_schluessel, editable=False)  # fmt: skip
    nebeneinander = models.PositiveSmallIntegerField(
        "Seiten gleichzeitig", default=1,
        choices=[(1, "eine Seite, die Seiten wechseln sich ab"), (2, "zwei Seiten nebeneinander")],
    )  # fmt: skip
    sekunden = models.PositiveSmallIntegerField(
        "Sekunden je Seite", default=20, validators=[MinValueValidator(5), MaxValueValidator(600)],
        help_text="Wie lange eine Seite stehen bleibt, bevor die nächste kommt.",
    )  # fmt: skip
    qr_code = models.BooleanField(
        "QR-Code fürs Handy", default=True,
        help_text="In der großen Ansicht eines Plans steht ein QR-Code: mit dem eigenen Handy "
        "scannen, mit dem eigenen Konto anmelden und dort ändern.",
    )  # fmt: skip
    aendern = models.BooleanField(
        "Ändern am Monitor", default=True,
        help_text="Auf einen Platz tippen und mit Name und persönlicher PIN bestätigen: sich "
        "austragen, einspringen; wer planen darf, auch Ersatz und Gäste eintragen.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Aushang-Monitor"
        verbose_name_plural = "Aushang-Monitore"
        ordering = ["name"]

    def __str__(self):
        return self.name


class AushangSeite(models.Model):
    """Eine Seite auf dem Monitor: Seitenart eines Moduls (``Modul.aushang``) und ihre Wahl."""

    MONATE = [(1, "dieser Monat"), (2, "dieser und nächster Monat")]

    aushang = models.ForeignKey(Aushang, on_delete=models.CASCADE, related_name="seiten")
    art = models.CharField("Seite", max_length=40)
    wert = models.CharField("Auswahl", max_length=40, blank=True)
    monate = models.PositiveSmallIntegerField("Zeitraum", choices=MONATE, default=2)
    # Statt ganzer Monate die nächsten Wochen ab heute (vergangene Tage fallen weg); 0 = Monate
    wochen = models.PositiveSmallIntegerField("Wochen", default=0)
    reihenfolge = models.PositiveIntegerField("Reihenfolge", default=0)

    class Meta:
        verbose_name = "Seite eines Aushang-Monitors"
        verbose_name_plural = "Seiten der Aushang-Monitore"
        ordering = ["reihenfolge", "pk"]

    def __str__(self):
        return f"{self.art} {self.wert}".strip()

    def zeitraum_text(self) -> str:
        if self.wochen:
            return f"die nächsten {self.wochen} Wochen ab heute"
        return self.get_monate_display()


class MonitorPin(models.Model):
    """Persönliche PIN einer Person für das Ändern am Aushang-Monitor (gehasht wie ein Passwort).
    Nach ``VERSUCHE`` falschen Eingaben ist sie ``SPERRE`` lang gesperrt."""

    VERSUCHE = 5
    SPERRE_MINUTEN = 15

    benutzer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="monitor_pin")  # fmt: skip
    pin = models.CharField("PIN", max_length=128)
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)
    fehler = models.PositiveSmallIntegerField(default=0)
    gesperrt_bis = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "PIN für Aushang-Monitore"
        verbose_name_plural = "PINs für Aushang-Monitore"

    def __str__(self):
        return f"PIN von {self.benutzer}"


auditlog.register(Aushang, exclude_fields=["schluessel"])
auditlog.register(MonitorPin, exclude_fields=["pin", "fehler", "gesperrt_bis", "geaendert_am"])
auditlog.register(AushangSeite)
