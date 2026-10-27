"""Fahrdienst: Touren, feste Besetzung je Wochentag, Springer, Ausfälle und Ersatz (ADR 0074).

Der Plan eines Tages entsteht aus der festen Besetzung (``Besetzung``) des Wochentags; wer an
dem Tag ausfällt (``Ausfall``), ist markiert, und ein ``Ersatz`` belegt den Platz für diesen Tag.
Die Regeln stehen in ``apps/fahrdienst/plan.py``.
"""

from auditlog.registry import auditlog
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.ausgabe.ampel import WOCHENTAGE
from apps.core.auswahl import FAHRDIENST_AUSFALLGRUENDE


class FahrdienstEinstellungen(models.Model):
    """Einstellungen des Fahrdienstes (Singleton)."""

    EINZIGE_ID = 1

    selbst_melden = models.BooleanField(
        "Fahrer und Beifahrer melden ihren Ausfall selbst", default=True,
        help_text="Aus: Nur wer den Fahrdienst plant, trägt Ausfälle ein.",
    )  # fmt: skip
    benachrichtigen = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="+",
        verbose_name="Bei einem Ausfall benachrichtigen",
        help_text="Per E-Mail. Leer = alle, die den Fahrdienst planen dürfen.",
    )  # fmt: skip
    fahrtage = models.CharField(
        "Fahrtage", max_length=40, default="Mo, Di, Mi, Do, Fr",
        help_text="Wochentage, an denen die Touren fahren, z. B. „Mo, Di, Mi, Do, Fr“.",
    )  # fmt: skip
    feiertage_frei = models.BooleanField(
        "An Feiertagen keine Touren", default=True,
        help_text="Gesetzliche Feiertage des Bundeslands aus den Einstellungen der Tafel.",
    )  # fmt: skip
    telegram_schluessel_verschluesselt = models.TextField(blank=True, editable=False)
    telegram_chats = models.CharField(
        "Telegram-Chats", max_length=200, blank=True,
        help_text="Chat-IDs, mehrere mit Komma. Am einfachsten: Die Person schreibt dem Bot "
        "„/start“, dann unten „Chats suchen“.",
    )  # fmt: skip
    aufbewahren_monate = models.PositiveSmallIntegerField(
        "Ausfälle und Ersatz aufbewahren (Monate)", default=12,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Danach löscht bintafeln sie automatisch.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Fahrdienst-Einstellungen"
        verbose_name_plural = "Fahrdienst-Einstellungen"

    def __str__(self):
        return "Fahrdienst-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "FahrdienstEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


class Tour(models.Model):
    name = models.CharField("Name", max_length=60, unique=True)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    plaetze = models.PositiveSmallIntegerField(
        "Plätze", default=3, validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="Platz 1 ist Fahrer bzw. Fahrerin, die übrigen Beifahrer.",
    )  # fmt: skip
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Tour"
        verbose_name_plural = "Touren"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


def platz_name(platz: int) -> str:
    return "Fahrer" if platz == 1 else "Beifahrer"


class Besetzung(models.Model):
    """Wer an einem Wochentag regelmäßig auf einem Platz einer Tour fährt."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="besetzungen")
    wochentag = models.CharField("Wochentag", max_length=2,
                                 choices=[(t, t) for t in WOCHENTAGE])  # fmt: skip
    platz = models.PositiveSmallIntegerField("Platz")
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name="fahrdienst_besetzungen")  # fmt: skip

    class Meta:
        verbose_name = "Feste Besetzung"
        verbose_name_plural = "Feste Besetzungen"
        constraints = [
            models.UniqueConstraint(
                fields=["tour", "wochentag", "platz"], name="besetzung_eindeutig"
            )  # fmt: skip
        ]

    def __str__(self):
        return f"{self.tour} {self.wochentag} {platz_name(self.platz)}: {self.benutzer}"


class Springer(models.Model):
    """Springt bei Ausfällen ein, auf jeder Tour."""

    benutzer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="fahrdienst_springer")  # fmt: skip
    wochentage = models.CharField(
        "Nur an diesen Tagen", max_length=40, blank=True,
        help_text="z. B. „Mi“; leer = an allen Fahrtagen.",
    )  # fmt: skip
    anmerkung = models.CharField("Anmerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Springer"
        verbose_name_plural = "Springer"

    def __str__(self):
        return str(self.benutzer)


class Ausfall(models.Model):
    """Jemand kann an einem oder mehreren Tagen nicht fahren (der „gelbe Aufkleber“)."""

    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name="fahrdienst_ausfaelle")  # fmt: skip
    von = models.DateField("Von")
    bis = models.DateField("Bis")
    grund = models.CharField("Grund", max_length=20, choices=FAHRDIENST_AUSFALLGRUENDE,
                             default="sonstiges")  # fmt: skip
    anmerkung = models.CharField("Anmerkung", max_length=200, blank=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=150, blank=True)
    eingetragen_am = models.DateTimeField("Eingetragen am", auto_now_add=True)

    class Meta:
        verbose_name = "Ausfall"
        verbose_name_plural = "Ausfälle"
        ordering = ["von", "pk"]

    def __str__(self):
        zeit = f"{self.von:%d.%m.%Y}" + (f"–{self.bis:%d.%m.%Y}" if self.bis != self.von else "")
        return f"{self.benutzer} {zeit}"


class Ersatz(models.Model):
    """Wer an einem Tag einen Platz übernimmt."""

    datum = models.DateField("Datum")
    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="+")
    platz = models.PositiveSmallIntegerField("Platz")
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name="fahrdienst_ersatz")  # fmt: skip
    eingetragen_von = models.CharField("Eingetragen von", max_length=150, blank=True)
    eingetragen_am = models.DateTimeField("Eingetragen am", auto_now_add=True)

    class Meta:
        verbose_name = "Ersatz"
        verbose_name_plural = "Ersatz"
        constraints = [
            models.UniqueConstraint(fields=["datum", "tour", "platz"], name="ersatz_eindeutig")
        ]

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.tour} {platz_name(self.platz)}: {self.benutzer}"


auditlog.register(
    FahrdienstEinstellungen,
    m2m_fields={"benachrichtigen"},
    exclude_fields=["telegram_schluessel_verschluesselt"],
)
auditlog.register(Tour)
auditlog.register(Besetzung)
auditlog.register(Springer)
auditlog.register(Ausfall)
auditlog.register(Ersatz)
