"""Angebote mit Anmeldung (ADR 0131): z. B. ein Kochkurs, für den am Einlass Interessierte
gesammelt werden. Die Einträge hängen wie Notizen und Teilnahmen an der Kundennummer und
überstehen so einen Import des Kundenstamms."""

from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Angebot(models.Model):
    bezeichnung = models.CharField(
        "Bezeichnung", max_length=100, help_text="z. B. „Kochkurs Frühjahr“"
    )
    beschreibung = models.TextField(
        "Beschreibung für den Einlass", blank=True,
        help_text="Kurz, was es ist, wann und wo – z. B. „4 Abende, dienstags 17–19 Uhr, ab "
        "3. März, Gemeindehaus“. Erscheint am Einlass und auf der Liste.",
    )  # fmt: skip
    anmeldung_von = models.DateField("Anmeldung von")
    anmeldung_bis = models.DateField("Anmeldung bis einschließlich")
    plaetze = models.PositiveSmallIntegerField(
        "Plätze", help_text="So viele können teilnehmen, z. B. 12."
    )
    hoechstens = models.PositiveSmallIntegerField(
        "Interessierte höchstens",
        help_text="Bei dieser Zahl schließt die Liste von selbst, z. B. 20. So bleibt etwas "
        "Reserve für Absagen, ohne dass der Einlass weiterfragt.",
    )
    geschlossen = models.BooleanField(
        "Anmeldung geschlossen", default=False,
        help_text="Von Hand schließen, auch wenn die Höchstzahl noch nicht erreicht ist.",
    )  # fmt: skip
    endet_am = models.DateField(
        "Angebot endet am", null=True, blank=True,
        help_text="Letzter Termin. Danach läuft die Löschfrist. Leer: das Ende der Anmeldung.",
    )  # fmt: skip
    loeschen_nach_tagen = models.PositiveSmallIntegerField(
        "Interessierte löschen nach … Tagen", default=90,
        help_text="So viele Tage nach dem Ende werden die Einträge der Kunden gelöscht.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Angebot mit Anmeldung"
        verbose_name_plural = "Angebote mit Anmeldung"
        ordering = ["-anmeldung_von", "bezeichnung"]

    def __str__(self):
        return self.bezeichnung

    def clean(self):
        if self.anmeldung_von and self.anmeldung_bis and self.anmeldung_bis < self.anmeldung_von:
            raise ValidationError({"anmeldung_bis": "„Bis“ darf nicht vor „Von“ liegen."})
        if self.plaetze is not None and self.hoechstens is not None:
            if self.plaetze < 1:
                raise ValidationError({"plaetze": "Mindestens ein Platz."})
            if self.hoechstens < self.plaetze:
                raise ValidationError(
                    {"hoechstens": "Mindestens so viele Interessierte wie Plätze."}
                )
        if self.endet_am and self.anmeldung_von and self.endet_am < self.anmeldung_von:
            raise ValidationError({"endet_am": "Das Ende liegt vor dem Beginn der Anmeldung."})

    @property
    def ende(self):
        return self.endet_am or self.anmeldung_bis


class Interesse(models.Model):
    """Eine Person aus einem Haushalt hat Interesse an einem Angebot. Name und Geburtsdatum sind
    festgehalten, wie sie beim Eintragen im Kundenstamm standen (Personen haben nach einem
    Import andere Kennungen); die Kundennummer verbindet den Eintrag mit dem Haushalt."""

    class Stand(models.TextChoices):
        INTERESSIERT = "interessiert", "interessiert"
        ZUGESAGT = "zugesagt", "Platz zugesagt"
        NACHRUECKER = "nachruecker", "Nachrücker"
        ABGESAGT = "abgesagt", "abgesagt"

    angebot = models.ForeignKey(Angebot, on_delete=models.CASCADE, related_name="interessierte")
    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    ausgabestelle = models.ForeignKey(
        "kunden.Ausgabestelle", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Eingetragen an",
    )  # fmt: skip
    eingetragen_am = models.DateTimeField("Eingetragen am", default=timezone.now)
    eingetragen_von = models.CharField("Eingetragen von", max_length=150, blank=True)
    stand = models.CharField(
        "Stand", max_length=15, choices=Stand.choices, default=Stand.INTERESSIERT
    )

    class Meta:
        verbose_name = "Interessierte Person"
        verbose_name_plural = "Interessierte"
        ordering = ["eingetragen_am", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["angebot", "kundennummer", "vorname", "nachname", "geburtsdatum"],
                name="angebote_interesse_einmal",
                nulls_distinct=False,
            )  # fmt: skip
        ]

    def __str__(self):
        return f"{self.vorname} {self.nachname} ({self.angebot})"

    @property
    def name(self) -> str:
        return f"{self.vorname} {self.nachname}".strip()


auditlog.register(Angebot)
auditlog.register(Interesse)
