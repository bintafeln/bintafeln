"""Dienstplan der Ausgabe (ADR 0077): Aufgaben je Ausgabestelle und Ausgabetag, feste Besetzung,
Ausfälle und Ersatz – wie der Fahrdienst (ADR 0074), aber je Ausgabestelle und mit Teamleitung
je Ausgabetag, die bei einem Ausfall benachrichtigt wird.

Eingeteilt werden ``Helfer``: mit Konto (dann melden sie ihren Ausfall selbst) oder nur mit Name
und Telefon. Der Plan eines Tages entsteht aus der festen ``Besetzung`` der Aufgaben dieses
Wochentags; Regeln in ``apps/dienstplan/plan.py``.
"""

from auditlog.registry import auditlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.ausgabe.ampel import WOCHENTAGE
from apps.core.auswahl import FAHRDIENST_AUSFALLGRUENDE

TAG_WAHL = [(t, t) for t in WOCHENTAGE]


class DienstplanEinstellungen(models.Model):
    """Einstellungen des Dienstplans (Singleton)."""

    EINZIGE_ID = 1

    selbst_melden = models.BooleanField(
        "Helfer mit Konto melden ihren Ausfall selbst", default=True,
        help_text="Aus: Nur wer den Dienstplan plant, trägt Ausfälle ein.",
    )  # fmt: skip
    feiertage_frei = models.BooleanField(
        "An Feiertagen keine Ausgabe", default=True,
        help_text="Gesetzliche Feiertage des Bundeslands aus den Einstellungen der Tafel.",
    )  # fmt: skip
    telegram_schluessel_verschluesselt = models.TextField(blank=True, editable=False)
    telegram_chats = models.CharField(
        "Telegram-Chats", max_length=200, blank=True,
        help_text="Chat-IDs, mehrere mit Komma. Die Person schreibt dem Bot „/start“, dann unten "
        "„Chats suchen“.",
    )  # fmt: skip
    aufbewahren_monate = models.PositiveSmallIntegerField(
        "Ausfälle und Ersatz aufbewahren (Monate)", default=12,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Danach löscht bintafeln sie automatisch.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Dienstplan-Einstellungen"
        verbose_name_plural = "Dienstplan-Einstellungen"

    def __str__(self):
        return "Dienstplan-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "DienstplanEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


class Helfer(models.Model):
    """Wer in der Ausgabe eingeteilt werden kann – mit Konto oder nur mit Namen."""

    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name="dienstplan_helfer", verbose_name="Konto",
        help_text="Mit Konto sieht die Person den Plan und meldet ihren Ausfall selbst.",
    )  # fmt: skip
    name = models.CharField("Name", max_length=150, blank=True,
                            help_text="Nur ohne Konto nötig.")  # fmt: skip
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True,
                              help_text="Für Benachrichtigungen als Teamleitung; mit Konto "
                              "zählt die E-Mail des Kontos.")  # fmt: skip
    aktiv = models.BooleanField("Aktiv", default=True)
    anmerkung = models.CharField("Anmerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Helfer"
        verbose_name_plural = "Helfer"
        ordering = ["name"]

    def __str__(self):
        return self.anzeige

    @property
    def anzeige(self) -> str:
        if self.benutzer_id:
            return self.benutzer.get_full_name() or self.benutzer.get_username()
        return self.name

    @property
    def mail(self) -> str:
        return (self.benutzer.email if self.benutzer_id else "") or self.email

    @property
    def tel(self) -> str:
        if self.telefon or not self.benutzer_id:
            return self.telefon
        stamm = getattr(self.benutzer, "stammdaten", None)
        return stamm.telefon if stamm else ""

    def clean(self):
        if not self.benutzer_id and not self.name.strip():
            raise ValidationError("Bitte ein Konto wählen oder einen Namen eintragen.")


class DienstStelle(models.Model):
    """Eine Ausgabestelle im Dienstplan: ob sie mitmacht und an welchen Tagen Ausgabe ist."""

    ausgabestelle = models.OneToOneField("kunden.Ausgabestelle", on_delete=models.CASCADE,
                                         related_name="dienstplan")  # fmt: skip
    aktiv = models.BooleanField(
        "Dienstplan an dieser Ausgabestelle", default=False,
        help_text="Aus: Die Ausgabestelle erscheint im Dienstplan nicht.",
    )  # fmt: skip
    tage = models.CharField("Ausgabetage", max_length=40, blank=True,
                            help_text="z. B. „Mo, Mi, Fr“.")  # fmt: skip

    class Meta:
        verbose_name = "Ausgabestelle im Dienstplan"
        verbose_name_plural = "Ausgabestellen im Dienstplan"

    def __str__(self):
        return str(self.ausgabestelle)


class Diensttag(models.Model):
    """Ein Ausgabetag einer Stelle: wer leitet das Team (bekommt Ausfälle gemeldet)."""

    stelle = models.ForeignKey(DienstStelle, on_delete=models.CASCADE, related_name="diensttage")
    wochentag = models.CharField("Wochentag", max_length=2, choices=TAG_WAHL)
    teamleitung = models.ForeignKey(
        Helfer, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Teamleitung",
        help_text="Bekommt Ausfälle dieses Tages per E-Mail. Leer = alle, die planen dürfen.",
    )  # fmt: skip
    telefon = models.CharField(
        "Abmeldungen unter", max_length=50, blank=True,
        help_text="Steht unten im PDF; leer = Telefon der Teamleitung.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Ausgabetag"
        verbose_name_plural = "Ausgabetage"
        constraints = [models.UniqueConstraint(fields=["stelle", "wochentag"],
                                               name="diensttag_eindeutig")]  # fmt: skip

    def __str__(self):
        return f"{self.stelle} {self.wochentag}"


class Aufgabe(models.Model):
    """Eine Zeile im Plan, z. B. „Kasse 09:00–15:00“; mehrere gleiche (z. B. 4× Obst) möglich."""

    stelle = models.ForeignKey(DienstStelle, on_delete=models.CASCADE, related_name="aufgaben")
    wochentag = models.CharField("Wochentag", max_length=2, choices=TAG_WAHL)
    name = models.CharField("Aufgabe", max_length=60, blank=True,
                            help_text="Leer = weitere Zeile zur Aufgabe darüber.")  # fmt: skip
    von = models.TimeField("Von", null=True, blank=True)
    bis = models.TimeField("Bis", null=True, blank=True)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    pflicht = models.BooleanField(
        "Muss besetzt sein", default=True,
        help_text="Aus (z. B. Springer): ein leerer Platz ist nicht gelb markiert.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Aufgabe"
        verbose_name_plural = "Aufgaben"
        ordering = ["reihenfolge", "pk"]

    def __str__(self):
        return f"{self.name or '…'} {self.zeit}".strip()

    @property
    def zeit(self) -> str:
        if self.von and self.bis:
            return f"{self.von:%H.%M}-{self.bis:%H.%M}"
        return f"{self.von:%H.%M}" if self.von else ""


class Besetzung(models.Model):
    """Wer eine Aufgabe regelmäßig übernimmt (jede Woche an diesem Wochentag)."""

    aufgabe = models.OneToOneField(Aufgabe, on_delete=models.CASCADE, related_name="besetzung")
    helfer = models.ForeignKey(Helfer, on_delete=models.CASCADE, related_name="besetzungen")

    class Meta:
        verbose_name = "Feste Besetzung"
        verbose_name_plural = "Feste Besetzungen"

    def __str__(self):
        return f"{self.aufgabe}: {self.helfer}"


class Ausfall(models.Model):
    """Jemand kann an einem oder mehreren Tagen nicht."""

    helfer = models.ForeignKey(Helfer, on_delete=models.CASCADE, related_name="ausfaelle")
    von = models.DateField("Von")
    bis = models.DateField("Bis")
    grund = models.CharField("Grund", max_length=20, choices=FAHRDIENST_AUSFALLGRUENDE,
                             default="sonstiges")  # fmt: skip
    anmerkung = models.CharField("Anmerkung", max_length=200, blank=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=150, blank=True)
    eingetragen_am = models.DateTimeField("Eingetragen am", auto_now_add=True)
    # Wieder gesund gemeldet (ADR 0085): kann ab dann einspringen, feste Plätze bleiben frei
    gesund_ab = models.DateField("Wieder da ab", null=True, blank=True)

    class Meta:
        verbose_name = "Ausfall"
        verbose_name_plural = "Ausfälle"
        ordering = ["von", "pk"]

    def __str__(self):
        zeit = f"{self.von:%d.%m.%Y}" + (f"–{self.bis:%d.%m.%Y}" if self.bis != self.von else "")
        return f"{self.helfer} {zeit}"


class Ersatz(models.Model):
    """Wer an einem Tag eine Aufgabe übernimmt: ein Helfer oder ein Gast mit Namen."""

    datum = models.DateField("Datum")
    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.CASCADE, related_name="+")
    helfer = models.ForeignKey(Helfer, on_delete=models.CASCADE, null=True, blank=True,
                               related_name="ersatz")  # fmt: skip
    gast = models.CharField("Gast", max_length=100, blank=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=150, blank=True)
    eingetragen_am = models.DateTimeField("Eingetragen am", auto_now_add=True)

    class Meta:
        verbose_name = "Ersatz"
        verbose_name_plural = "Ersatz"
        constraints = [models.UniqueConstraint(fields=["datum", "aufgabe"],
                                               name="dienst_ersatz_eindeutig")]  # fmt: skip

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.aufgabe}: {self.helfer or f'{self.gast} (Gast)'}"


auditlog.register(DienstplanEinstellungen, exclude_fields=["telegram_schluessel_verschluesselt"])
auditlog.register(Helfer)
auditlog.register(DienstStelle)
auditlog.register(Diensttag)
auditlog.register(Aufgabe)
auditlog.register(Besetzung)
auditlog.register(Ausfall)
auditlog.register(Ersatz)
