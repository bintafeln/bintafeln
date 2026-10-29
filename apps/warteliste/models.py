"""Warteliste mit Einladungen (Modul, ADR 0051), aufgebaut auf den Anträgen (ADR 0024).

Jeder Antrag, der nicht im Papierkorb liegt, hat einen ``Wartestand``: wo er in der Warteliste
steht (wartend, eingeladen, erschienen …) und zu welchem Termin er eingeladen ist. Regeln in
``apps/warteliste/ablauf.py``.
"""

from auditlog.registry import auditlog
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.antraege.models import Antrag
from apps.kunden.models import Zusatzfeld

PLATZHALTER = "{vorname}, {nachname}, {datum}, {von}, {bis}, {ort}"


class WartelisteText(models.Model):
    """Eigene Übersetzung der Einladungs- und Absagetexte in eine Sprache (von Hand oder mit KI).
    Leere Felder: mitgelieferte Übersetzung, solange der deutsche Text der Vorgabe entspricht."""

    sprache = models.CharField("Sprache", max_length=10, unique=True)
    betreff = models.CharField("Betreff", max_length=300, blank=True)
    anrede = models.CharField("Anrede", max_length=300, blank=True)
    einleitung = models.TextField("Einleitung", blank=True)
    schluss = models.TextField("Text nach dem Termin", blank=True)
    mitbringen = models.TextField("Bitte mitbringen (eine Zeile je Punkt)", blank=True)
    gruss = models.TextField("Gruß", blank=True)
    absage_betreff = models.CharField("Betreff der Absage", max_length=300, blank=True)
    absage_text = models.TextField("Text der Absage", blank=True)

    class Meta:
        verbose_name = "Einladungstext je Sprache"
        verbose_name_plural = "Einladungstexte je Sprache"

    def __str__(self):
        return self.sprache


class WartelisteEinstellungen(models.Model):
    """Einstellungen der Warteliste (Singleton)."""

    EINZIGE_ID = 1

    class Automatik(models.TextChoices):
        AUS = "aus", "aus – Status bleibt „eingeladen“"
        MOEGLICH = "moeglich", "auf „Streichen möglich“ setzen (Team entscheidet)"
        STREICHEN = "streichen", "direkt streichen"

    streichen_nach_tagen = models.PositiveSmallIntegerField(
        "Tage nach dem Termin ohne Rückmeldung", default=15,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
    )  # fmt: skip
    automatik = models.CharField("Dann", max_length=10, choices=Automatik.choices,
                                 default=Automatik.MOEGLICH)  # fmt: skip
    sperrzeit_monate = models.PositiveSmallIntegerField(
        "Sperrzeit nach Ablauf des Ausweises (Monate)", default=12,
        validators=[MaxValueValidator(60)],
        help_text="Wer schon Kunde war, kann sich erst so lange nach Ablauf des Ausweises neu "
        "anmelden. 0 = keine Sperrzeit. Wird im Abgleich mit dem Kundenstamm angezeigt.",
    )  # fmt: skip
    ausnahme_ab_alter = models.PositiveSmallIntegerField(
        "Keine Sperrzeit ab Alter", null=True, blank=True, default=60,
        validators=[MaxValueValidator(120)], help_text="Leer = keine Altersausnahme.",
    )  # fmt: skip
    ausnahme_feld = models.ForeignKey(
        Zusatzfeld, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Keine Sperrzeit bei", limit_choices_to={"typ": Zusatzfeld.Typ.JA_NEIN},
        help_text="Ja/Nein-Zusatzfeld im Kundenstamm, z. B. „Schwerbehindert“.",
    )  # fmt: skip
    streichungsliste_tage = models.PositiveSmallIntegerField(
        "Streichungsliste aufbewahren (Tage)", default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
    )  # fmt: skip
    ort = models.TextField(
        "Ort der Termine", blank=True,
        help_text="Steht in der Einladung. Leer = Name und Anschrift der Tafel.",
    )  # fmt: skip
    betreff = models.CharField("Betreff", max_length=200,
                               default="Einladung zur Anmeldung – {datum}")  # fmt: skip
    anrede = models.CharField("Anrede", max_length=200, default="Guten Tag {vorname} {nachname}")
    einleitung = models.TextField(
        "Einleitung", default="wir können Ihnen folgenden Termin anbieten:"
    )
    schluss = models.TextField(
        "Text nach dem Termin", blank=True,
        default="Bei dem Termin kann es zu Wartezeiten kommen, da mehrere Personen eingeladen "
        "wurden.",
    )  # fmt: skip
    mitbringen = models.TextField(
        "Bitte mitbringen (eine Zeile je Punkt)", blank=True,
        default="Aktueller Bescheid (Bürgergeld, Grundsicherung, Wohngeld …)\n"
        "Personalausweise aller Personen auf dem Bescheid",
    )  # fmt: skip
    gruss = models.TextField("Gruß", default="Mit freundlichen Grüßen\nIhr Tafel-Team")
    absage_betreff = models.CharField("Betreff der Absage", max_length=200,
                                      default="Termin entfällt – {datum}")  # fmt: skip
    absage_text = models.TextField(
        "Text der Absage",
        default="leider müssen wir den Termin absagen. Sie bekommen in Kürze einen neuen Termin.",
    )  # fmt: skip

    TEXTFELDER = ["betreff", "anrede", "einleitung", "schluss", "mitbringen", "gruss",
                  "absage_betreff", "absage_text"]  # fmt: skip

    class Meta:
        verbose_name = "Warteliste-Einstellungen"
        verbose_name_plural = "Warteliste-Einstellungen"

    def __str__(self):
        return "Warteliste-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "WartelisteEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


class Termin(models.Model):
    """Termin, zu dem Antragsteller eingeladen werden (z. B. Anmeldung im Büro)."""

    datum = models.DateField("Datum")
    von = models.TimeField("von")
    bis = models.TimeField("bis", null=True, blank=True)
    ort = models.TextField("Ort", blank=True, help_text="Leer = Ort aus den Einstellungen.")
    anmerkung = models.CharField("Anmerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Termin"
        verbose_name_plural = "Termine"
        ordering = ["datum", "von"]

    def __str__(self):
        bis = f"–{self.bis:%H:%M}" if self.bis else ""
        return f"{self.datum:%d.%m.%Y} {self.von:%H:%M}{bis} Uhr"


class Wartestand(models.Model):
    class Status(models.TextChoices):
        NEU = "neu", "neu"
        WARTEND = "wartend", "wartend"
        WARTEZEIT = "wartezeit", "Wartezeit"
        WARTEZEIT_UM = "wz_abgelaufen", "Wartezeit abgelaufen"
        EINGELADEN = "eingeladen", "eingeladen"
        STREICHEN_MOEGLICH = "streichen_moeglich", "Streichen möglich"
        ERSCHIENEN = "erschienen", "erschienen"
        ENTSCHULDIGT = "entschuldigt", "entschuldigt"
        GESTRICHEN = "gestrichen", "gestrichen"
        AUFGENOMMEN = "aufgenommen", "aufgenommen"

    # Ausgeblendet, solange man nicht danach filtert
    ABGESCHLOSSEN = (Status.GESTRICHEN, Status.AUFGENOMMEN)

    antrag = models.OneToOneField(Antrag, on_delete=models.CASCADE, related_name="wartestand")
    status = models.CharField("Status", max_length=20, choices=Status.choices,
                              default=Status.NEU)  # fmt: skip
    wartezeit_bis = models.DateField("Wartezeit bis", null=True, blank=True)
    termin = models.ForeignKey(Termin, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="wartende", verbose_name="Termin")  # fmt: skip
    eingeladen_am = models.DateTimeField("Eingeladen am", null=True, blank=True)
    geaendert_am = models.DateTimeField("Geändert am", default=timezone.now)

    class Meta:
        verbose_name = "Wartestand"
        verbose_name_plural = "Wartestände"

    def __str__(self):
        return f"Antrag {self.antrag.nummer}: {self.get_status_display()}"


class Einladung(models.Model):
    """Verlauf: Einladungen und Absagen je Antrag (auch ohne Mail, z. B. per Telefon)."""

    class Art(models.TextChoices):
        EINLADUNG = "einladung", "Einladung"
        ABSAGE = "absage", "Absage"

    antrag = models.ForeignKey(Antrag, on_delete=models.CASCADE, related_name="einladungen")
    termin = models.ForeignKey(Termin, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="einladungen")  # fmt: skip
    termin_text = models.CharField("Termin", max_length=100)
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.EINLADUNG)
    weg = models.CharField("Weg", max_length=20, default="E-Mail")
    gesendet_am = models.DateTimeField("Am", default=timezone.now)
    von = models.CharField("Von", max_length=150, blank=True)
    fehler = models.CharField("Fehler", max_length=300, blank=True)

    class Meta:
        verbose_name = "Einladung"
        verbose_name_plural = "Einladungen"
        ordering = ["gesendet_am"]

    def __str__(self):
        return f"{self.get_art_display()} {self.termin_text}"


class Streichung(models.Model):
    """Eintrag der Streichungsliste (wird nach ``streichungsliste_tage`` gelöscht)."""

    class Weg(models.TextChoices):
        HAND = "hand", "von Hand"
        AUTOMATIK = "automatik", "automatisch"
        DUBLETTE = "dublette", "doppelter Antrag"

    antragsnummer = models.CharField("Antrag", max_length=20)
    name = models.CharField("Name", max_length=210)
    termin_text = models.CharField("Letzter Termin", max_length=100, blank=True)
    weg = models.CharField("Gestrichen", max_length=10, choices=Weg.choices, default=Weg.HAND)
    gestrichen_am = models.DateTimeField("Gestrichen am", default=timezone.now)
    von = models.CharField("Von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Streichung"
        verbose_name_plural = "Streichungsliste"
        ordering = ["-gestrichen_am"]

    def __str__(self):
        return f"Streichung Antrag {self.antragsnummer}"


class DubletteIgnoriert(models.Model):
    """Zwei Anträge, die das Team als „keine Dublette“ markiert hat (kleinere pk zuerst)."""

    a = models.ForeignKey(Antrag, on_delete=models.CASCADE, related_name="+")
    b = models.ForeignKey(Antrag, on_delete=models.CASCADE, related_name="+")
    von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                            blank=True, related_name="+")  # fmt: skip

    class Meta:
        verbose_name = "Keine Dublette"
        verbose_name_plural = "Keine Dubletten"
        constraints = [models.UniqueConstraint(fields=["a", "b"], name="dublette_paar_eindeutig")]

    def __str__(self):
        return f"Keine Dublette {self.a_id}/{self.b_id}"


auditlog.register(WartelisteEinstellungen)
auditlog.register(Termin)
auditlog.register(Wartestand)
auditlog.register(Einladung)
auditlog.register(Streichung)


class AbgleichEntscheidung(models.Model):
    """Ergebnis des Abgleichs mit dem Kundenstamm: Ist der ähnliche Haushalt derselbe?"""

    antrag = models.ForeignKey(Antrag, on_delete=models.CASCADE, related_name="abgleich")
    kundennummer = models.CharField("Kundennummer", max_length=20)
    gleich = models.BooleanField("Derselbe Haushalt")
    ergebnis = models.CharField("Ergebnis", max_length=300, blank=True)
    von = models.CharField("Von", max_length=150, blank=True)
    am = models.DateTimeField("Am", auto_now_add=True)

    class Meta:
        ordering = ["-am"]
        verbose_name = "Abgleich-Entscheidung"
        verbose_name_plural = "Abgleich-Entscheidungen"
        constraints = [models.UniqueConstraint(fields=["antrag", "kundennummer"],
                                               name="abgleich_einmal_je_kunde")]  # fmt: skip

    def __str__(self):
        return f"Antrag {self.antrag.nummer} / Kunde {self.kundennummer}"
