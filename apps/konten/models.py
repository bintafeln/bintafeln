from auditlog.registry import auditlog
from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
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
    ausgabestellen = models.ManyToManyField(
        "kunden.Ausgabestelle",
        blank=True,
        related_name="mitarbeitende",
        verbose_name="Ausgabestellen",
        help_text="Wer einer Ausgabestelle zugeordnet ist, ruft nur deren Kunden auf – außer "
        "mit dem Recht „Kunden aller Ausgabestellen aufrufen“. Leer: alle Kunden.",
    )
    kundenliste_aus = models.JSONField(
        "In der Kundenliste ausgeblendete Spalten", default=list, blank=True,
        help_text="Jede Person wählt auf der Kundenliste selbst, welche Spalten sie sieht.",
    )  # fmt: skip
    ausgabetage = models.CharField(
        "Ausgabetage", max_length=30, blank=True,
        help_text="An welchen Tagen die Person meist arbeitet; die Kundenliste startet mit diesem "
        "Tag.",
    )  # fmt: skip
    gewaehlte_stelle = models.ForeignKey(
        "kunden.Ausgabestelle", verbose_name="Gewählte Ausgabestelle", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
        help_text="Ausgabestelle aus dem Auswahlfeld oben im Menü; gilt bis zur nächsten Wahl "
        "(ADR 0067).",
    )  # fmt: skip
    papierkorb_gesehen_am = models.DateTimeField(
        "Papierkorb zuletzt angesehen", null=True, blank=True,
        help_text="Die Zahl im Menü zählt nur, was danach in den Papierkorb kam (ADR 0073).",
    )  # fmt: skip
    # Konto einer Ausgabestelle für die Einlass-Tablets (ADR 0059): Anmeldung mit dem Namen der
    # Ausgabestelle und Passwort, ohne Zwei-Faktor, Abmeldung nach 30 Minuten ohne Eingabe.
    stelle = models.OneToOneField(
        "kunden.Ausgabestelle", verbose_name="Konto der Ausgabestelle", null=True, blank=True,
        on_delete=models.PROTECT, related_name="konto",
    )  # fmt: skip

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"

    def __str__(self):
        return self.get_full_name() or self.username


class Stammdaten(models.Model):
    """Persönliche Angaben einer Mitarbeiterin oder eines Mitarbeiters (ADR 0017).

    Getrennt vom Konto, damit die Löschfrist nach dem Austritt sie leeren kann, während das
    Konto im Archiv nachvollziehbar bleibt.
    """

    benutzer = models.OneToOneField(
        Benutzer, on_delete=models.CASCADE, primary_key=True, related_name="stammdaten"
    )
    anrede = models.CharField("Anrede", max_length=30, blank=True)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    handy = models.CharField("Handy", max_length=50, blank=True)
    notfall_name = models.CharField("Notfallkontakt: Name", max_length=150, blank=True)
    notfall_telefon = models.CharField("Notfallkontakt: Telefon", max_length=50, blank=True)
    eintritt = models.DateField("Eintritt", null=True, blank=True)
    austritt = models.DateField("Austritt", null=True, blank=True)
    bemerkung = models.TextField("Anmerkung", blank=True)
    fs_klassen = models.CharField("Führerscheinklassen", max_length=100, blank=True)
    fs_gueltig_bis = models.DateField("Führerschein gültig bis", null=True, blank=True)
    fs_gesehen_am = models.DateField("Führerschein zuletzt gesehen am", null=True, blank=True)
    fs_gesehen_von = models.CharField("gesehen von", max_length=150, blank=True)
    ifsg_erstbelehrung_am = models.DateField("Erstbelehrung IfSG (§ 43) am", null=True, blank=True)
    ifsg_belehrung_am = models.DateField("Letzte Folgebelehrung IfSG am", null=True, blank=True)
    # Verschlüsselt unter MEDIA_ROOT/privat/; nur wenn die Tafel Kopien erlaubt (ADR 0017).
    fs_kopie_datei = models.CharField(max_length=200, blank=True, editable=False)
    fs_kopie_typ = models.CharField(max_length=100, blank=True, editable=False)
    fs_kopie_am = models.DateTimeField("Kopie hochgeladen am", null=True, blank=True)
    geleert_am = models.DateTimeField("Nach Löschfrist geleert am", null=True, blank=True)

    class Meta:
        verbose_name = "Stammdaten Mitarbeitende"
        verbose_name_plural = "Stammdaten Mitarbeitende"

    def __str__(self):
        return f"Stammdaten {self.benutzer}"

    @property
    def letzte_ifsg_belehrung(self):
        daten = [d for d in (self.ifsg_erstbelehrung_am, self.ifsg_belehrung_am) if d]
        return max(daten) if daten else None


class PersonalEinstellungen(models.Model):
    """Fristen rund um Mitarbeitende (Singleton)."""

    EINZIGE_ID = 1

    fs_pruefung_monate = models.PositiveSmallIntegerField(
        "Führerschein erneut ansehen nach … Monaten",
        default=0,
        validators=[MaxValueValidator(24)],
        help_text="0 = keine Wiedervorlage zum Führerschein (weder Ablauf noch Vorlegen).",
    )
    ifsg_wiederholung_monate = models.PositiveSmallIntegerField(
        "IfSG-Folgebelehrung alle … Monate",
        default=0,
        validators=[MaxValueValidator(60)],
        help_text="0 = keine Wiedervorlage zur Belehrung nach Infektionsschutzgesetz.",
    )
    vorlauf_tage = models.PositiveSmallIntegerField(
        "Wiedervorlage … Tage vorher anzeigen",
        default=14,
        validators=[MaxValueValidator(90)],
        help_text="0 = erst am Tag selbst.",
    )
    fs_kopie_erlaubt = models.BooleanField(
        "Kopie des Führerscheins speichern erlauben",
        default=False,
        help_text="In der Regel genügt der Vermerk „gesehen am / von“. Kopien werden "
        "verschlüsselt gespeichert, jeder Abruf wird protokolliert.",
    )
    urlaub_verfall_monat = models.PositiveSmallIntegerField(
        "Resturlaub verfällt im Folgejahr am … (Monat)",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    urlaub_verfall_tag = models.PositiveSmallIntegerField(
        "… (Tag)",
        default=31,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Vorgabe 31.03. Je Person und Jahr unter „Personal“ änderbar.",
    )
    stammdaten_loeschen_jahre = models.PositiveSmallIntegerField(
        "Stammdaten … Jahre nach Austritt bzw. Sperre leeren",
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Name, Rollen und Zeiträume bleiben im Archiv; Anschrift, Telefon, "
        "Notfallkontakt, Führerschein und Belehrungen werden geleert.",
    )

    class Meta:
        verbose_name = "Einstellungen Personal"
        verbose_name_plural = "Einstellungen Personal"

    def __str__(self):
        return "Einstellungen Personal"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "PersonalEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


auditlog.register(
    Benutzer,
    exclude_fields=["password", "last_login", "kundenliste_aus"],
    m2m_fields={"groups", "ausgabestellen"},
)


class Schulung(models.Model):
    benutzer = models.ForeignKey(Benutzer, on_delete=models.CASCADE, related_name="schulungen")
    thema = models.CharField("Thema", max_length=200)
    datum = models.DateField("Datum")
    gueltig_bis = models.DateField(
        "Gültig bis", null=True, blank=True, help_text="Leer = ohne Ablauf."
    )
    bemerkung = models.CharField("Anmerkung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Schulung"
        verbose_name_plural = "Schulungen"
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.thema} am {self.datum:%d.%m.%Y}"


class DokumentKategorie(models.Model):
    name = models.CharField("Name", max_length=100, unique=True)
    nur_personal = models.BooleanField(
        "Nur für Admin und Rolle Personal sichtbar",
        default=False,
        help_text="Z. B. Arbeitsverträge oder Lohnunterlagen.",
    )

    class Meta:
        verbose_name = "Dokumentkategorie"
        verbose_name_plural = "Dokumentkategorien"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Dokument(models.Model):
    """Dokument zu einer Person, verschlüsselt unter MEDIA_ROOT/privat/ (ADR 0017)."""

    ORDNER = "mitarbeiter-dokumente"
    PRIVATDATEI = (ORDNER, "datei")  # Papierkorb (ADR 0073)

    benutzer = models.ForeignKey(Benutzer, on_delete=models.CASCADE, related_name="dokumente")
    kategorie = models.ForeignKey(
        DokumentKategorie, verbose_name="Kategorie", on_delete=models.PROTECT
    )
    titel = models.CharField("Titel", max_length=200)
    datum = models.DateField("Dokumentdatum", null=True, blank=True)
    datei = models.CharField(max_length=200, editable=False)
    typ = models.CharField(max_length=100, editable=False)
    hochgeladen_am = models.DateTimeField("Hochgeladen am", default=timezone.now)
    hochgeladen_von = models.CharField("Hochgeladen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Dokument"
        verbose_name_plural = "Dokumente"
        ordering = ["-hochgeladen_am"]

    def __str__(self):
        return self.titel


class Rolle(models.Model):
    """Rechte und Pflichten einer Rolle (ADR 0033). Der Name ist der Name der Django-Gruppe."""

    gruppe = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="rolle")
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)
    rechte = models.JSONField("Rechte", default=list, blank=True)
    zwei_faktor_pflicht = models.BooleanField(
        "Zwei-Faktor-Anmeldung Pflicht",
        default=True,
        help_text="Wer diese Rolle hat, muss sich mit zweitem Faktor anmelden.",
    )
    braucht_belehrung = models.BooleanField(
        "Braucht Belehrung nach Infektionsschutzgesetz",
        default=False,
        help_text="Erinnerung an die Belehrung in den Stammdaten (z. B. Ausgabe, Fahrer).",
    )
    braucht_fuehrerschein = models.BooleanField(
        "Braucht Führerschein",
        default=False,
        help_text="Erinnerung an die Führerscheinkontrolle in den Stammdaten.",
    )
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=100)

    class Meta:
        verbose_name = "Rolle"
        verbose_name_plural = "Rollen"
        ordering = ["reihenfolge", "gruppe__name"]

    def __str__(self):
        return self.gruppe.name

    @property
    def name(self) -> str:
        return self.gruppe.name

    @property
    def ist_admin(self) -> bool:
        from apps.konten.rollen import ADMIN

        return self.gruppe.name == ADMIN


auditlog.register(Stammdaten, exclude_fields=["fs_kopie_datei"])
auditlog.register(DokumentKategorie)
auditlog.register(Dokument, exclude_fields=["datei"])
auditlog.register(Schulung)
auditlog.register(PersonalEinstellungen)
auditlog.register(Rolle)


@receiver(post_save, sender=Group)
def rolle_zur_gruppe(sender, instance, created, raw=False, **kwargs):
    """Jede Gruppe ist eine Rolle, auch wenn sie anders angelegt wurde (z. B. Django-Verwaltung).

    Nicht beim Einlesen von Rohdaten (Datensicherung): Dort kommt die Rolle aus der Datei."""
    if created and not raw:
        Rolle.objects.get_or_create(gruppe=instance, defaults={"zwei_faktor_pflicht": False})


# Nur, wer wann ein Gerät eingerichtet oder entfernt hat – nie Schlüssel oder Codes.
class AnmeldeEinstellungen(models.Model):
    """Einstellungen der Anmeldung (Singleton), z. B. vertraute Geräte bei Zwei-Faktor."""

    EINZIGE_ID = 1
    TAGE = [(0, "aus – immer Code eingeben"), (1, "1 Tag"), (7, "7 Tage"), (14, "14 Tage"),
            (30, "30 Tage"), (90, "90 Tage")]  # fmt: skip

    vertrauen_tage = models.PositiveSmallIntegerField(
        "Geräten vertrauen für", choices=TAGE, default=0,
        help_text="Wer bei der Anmeldung „Diesem Gerät vertrauen“ anhakt, braucht auf diesem "
        "Browser so lange keinen Zwei-Faktor-Code (das Passwort weiterhin). Gilt für alle Rollen.",
    )  # fmt: skip
    stellen_zwei_faktor = models.BooleanField(
        "Konten der Ausgabestellen dürfen Zwei-Faktor einrichten", default=False,
        help_text="Aus: Die Konten der Ausgabestellen sehen die Zwei-Faktor-Anmeldung nicht; beim "
        "Ausschalten werden dort eingerichtete Geräte entfernt (ADR 0059).",
    )  # fmt: skip

    class Meta:
        verbose_name = "Anmelde-Einstellungen"
        verbose_name_plural = "Anmelde-Einstellungen"

    def __str__(self):
        return "Anmelde-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "AnmeldeEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


class VertrautesGeraet(models.Model):
    """Browser, auf dem bis ``gueltig_bis`` kein Zwei-Faktor-Code nötig ist.

    Gespeichert ist nur eine Prüfsumme des Merkmals im Browser-Cookie und ein Stand des
    Passworts: Nach einer Passwortänderung gilt das Gerät nicht mehr.
    """

    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name="vertraute_geraete")  # fmt: skip
    pruefsumme = models.CharField(max_length=64, unique=True)
    passwort_stand = models.CharField(max_length=64)
    bezeichnung = models.CharField("Gerät", max_length=150, blank=True)
    angelegt_am = models.DateTimeField("Vertraut seit", default=timezone.now)
    gueltig_bis = models.DateTimeField("Gültig bis")
    zuletzt_am = models.DateTimeField("Zuletzt benutzt", null=True, blank=True)

    class Meta:
        verbose_name = "Vertrautes Gerät"
        verbose_name_plural = "Vertraute Geräte"
        ordering = ["-angelegt_am"]

    def __str__(self):
        return f"{self.bezeichnung or 'Gerät'} ({self.benutzer})"


auditlog.register(AnmeldeEinstellungen)
auditlog.register(VertrautesGeraet, exclude_fields=["pruefsumme", "passwort_stand"])
auditlog.register(TOTPDevice, include_fields=["user", "name", "confirmed"])
auditlog.register(StaticDevice, include_fields=["user", "name", "confirmed"])
