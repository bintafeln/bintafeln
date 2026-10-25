import uuid

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.core.farben import STANDARDFARBE, farbtoene
from apps.core.feiertage import BUNDESLAENDER


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
    farbe = models.CharField(
        "Farbe",
        max_length=7,
        default=STANDARDFARBE,
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Bitte eine Farbe wählen.")],
        help_text="Kopfzeile, Knöpfe und Links der ganzen Anwendung und des Antragsformulars. "
        "Voreingestellt ist Tafel-Orange.",
    )
    hintergrund_anmeldung = models.ImageField(
        "Hintergrundbild der Anmeldeseite", upload_to="oeffentlich/hintergrund/", blank=True,
        help_text="JPG, PNG oder WebP, höchstens 5 MB. Öffentlich abrufbar (auch vor der "
        "Anmeldung), also kein Bild mit Personen, die nicht zugestimmt haben.",
    )  # fmt: skip
    hintergrund = models.ImageField(
        "Hintergrundbild der übrigen Seiten", upload_to="oeffentlich/hintergrund/", blank=True,
        help_text="Leer = dasselbe Bild wie auf der Anmeldeseite.",
    )  # fmt: skip
    hintergrund_staerke = models.PositiveSmallIntegerField(
        "Stärke des Hintergrundbilds auf den übrigen Seiten (%)", default=15,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0 = nicht sichtbar, 100 = volle Stärke. Die Inhalte stehen immer auf weißen "
        "Karten und bleiben lesbar.",
    )  # fmt: skip
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    bundesland = models.CharField(
        "Bundesland",
        max_length=2,
        choices=BUNDESLAENDER,
        blank=True,
        help_text="Für die gesetzlichen Feiertage (Urlaub, Stundenkonto, Vorauszahlung).",
    )
    module = models.JSONField(
        "Eingeschaltete Module", default=list, blank=True,
        help_text="Kennungen der zuschaltbaren Module (ADR 0049), z. B. „aufruf“.",
    )  # fmt: skip
    installation = models.UUIDField(
        "Kennung dieser Installation", default=uuid.uuid4, editable=False
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

    @property
    def hintergrund_bild(self):
        """Bild der übrigen Seiten; ohne eigenes das der Anmeldeseite."""
        return self.hintergrund or self.hintergrund_anmeldung

    @property
    def hintergrund_deckkraft(self) -> str:
        """Für CSS opacity, immer mit Punkt (unabhängig von der Sprache)."""
        return f"{self.hintergrund_staerke / 100:.2f}"

    @classmethod
    def laden(cls) -> "TafelEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    def farben(self) -> dict[str, str]:
        """Aus der einen Farbe abgeleitete Töne für die CSS-Variablen."""
        return farbtoene(self.farbe)

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


class SicherungsAuftrag(models.Model):
    """Ein Auftrag für den Dienst "backup" (ADR 0042): wohin, wann, wie lange aufbewahren.

    Die Felder ab ``angefordert_am`` schreibt der Dienst selbst (Stand des letzten Laufs). Der
    Standard-Auftrag sichert in den Ordner aus BINTAFELN_SICHERUNG_PFAD; dorthin sichern auch
    „./betrieb sichern“ und das Update, und von dort stellt „./betrieb wiederherstellen“ her.
    """

    WOCHENTAGE = [("1", "Mo"), ("2", "Di"), ("3", "Mi"), ("4", "Do"), ("5", "Fr"), ("6", "Sa"),
                  ("7", "So")]  # fmt: skip

    name = models.CharField("Name", max_length=100)
    standard = models.BooleanField("Standard-Auftrag", default=False, editable=False)
    ziel = models.CharField(
        "Ziel", max_length=300, blank=True,
        help_text="Leer = Sicherungsordner des Servers; sonst ein Ordner unter /media oder /mnt.",
    )  # fmt: skip
    aktiv = models.BooleanField("Regelmäßig ausführen", default=True)
    wochentage = models.CharField("Wochentage", max_length=7, default="1234567")
    uhrzeit = models.TimeField("Uhrzeit")
    anzahl = models.PositiveSmallIntegerField(
        "Höchstens so viele Stände aufbewahren", null=True, blank=True
    )
    tage = models.PositiveSmallIntegerField("Stände höchstens so viele Tage aufbewahren",
                                            null=True, blank=True)  # fmt: skip
    angefordert_am = models.DateTimeField("Sofort-Sicherung angefordert am", null=True,
                                          blank=True)  # fmt: skip
    angefordert_von = models.CharField(max_length=150, blank=True)
    laeuft_seit = models.DateTimeField(null=True, blank=True, editable=False)
    geplant_am = models.DateField(null=True, blank=True, editable=False)
    letzter_versuch = models.DateTimeField(null=True, blank=True, editable=False)
    ergebnis = models.CharField(max_length=20, blank=True, editable=False)
    meldung = models.TextField(blank=True, editable=False)
    letzte_erfolgreiche = models.DateTimeField(null=True, blank=True, editable=False)
    staende = models.TextField(blank=True, editable=False)
    frei_bytes = models.BigIntegerField(null=True, blank=True, editable=False)
    gesamt_bytes = models.BigIntegerField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Sicherungsauftrag"
        verbose_name_plural = "Sicherungsaufträge"
        ordering = ["-standard", "name"]

    def __str__(self):
        return self.name

    @property
    def tage_namen(self) -> str:
        namen = [n for k, n in self.WOCHENTAGE if k in self.wochentage]
        if len(namen) == 7:
            return "täglich"
        if namen == ["Mo", "Di", "Mi", "Do", "Fr"]:
            return "Mo–Fr"
        return ", ".join(namen) or "nie"

    @property
    def staende_liste(self) -> list[tuple[str, int]]:
        """[(Name, Größe in Bytes)], neueste zuerst, wie der Dienst sie gemeldet hat."""
        ergebnis = []
        for zeile in self.staende.splitlines():
            name, _, kb = zeile.partition("|")
            if name:
                ergebnis.append((name, int(kb or 0) * 1024))
        return ergebnis


class SicherungsDienst(models.Model):
    """Lebenszeichen des Dienstes "backup" und die Ziele, die er sieht (eine Zeile, ADR 0042)."""

    EINZIGE_ID = 1
    letzter_kontakt = models.DateTimeField(null=True, blank=True)
    schluessel_ok = models.BooleanField(default=False)
    ziele = models.TextField(blank=True)

    class Meta:
        verbose_name = "Sicherungsdienst"
        verbose_name_plural = "Sicherungsdienst"

    def __str__(self):
        return "Sicherungsdienst"

    @classmethod
    def laden(cls):
        dienst, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return dienst

    def ziele_liste(self) -> list[tuple[str, int, int]]:
        """[(Pfad, frei, gesamt)] in Bytes."""
        ergebnis = []
        for zeile in self.ziele.splitlines():
            teile = zeile.split("|")
            if len(teile) == 3 and teile[0]:
                ergebnis.append((teile[0], int(teile[1] or 0) * 1024, int(teile[2] or 0) * 1024))
        return ergebnis


auditlog.register(TafelEinstellungen, exclude_fields=["geaendert_am"])
auditlog.register(
    SicherungsAuftrag,
    include_fields=["name", "ziel", "aktiv", "wochentage", "uhrzeit", "anzahl", "tage",
                    "angefordert_am", "angefordert_von"],
)  # fmt: skip
# Das (verschlüsselte) Passwort gehört nicht ins Änderungsprotokoll.
auditlog.register(MailEinstellungen, exclude_fields=["passwort_verschluesselt"])
