import datetime as dt
import uuid

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

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
    app_symbol = models.ImageField(
        "App-Symbol",
        upload_to="oeffentlich/app/",
        blank=True,
        help_text="Quadratisches Bild für den Browser-Tab und den Startbildschirm von Handy und "
        "Tablet (PNG, JPG oder WebP, höchstens 2 MB, am besten mindestens 512 × 512 Pixel). Leer = "
        "das Symbol von bintafeln. Öffentlich abrufbar.",
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
    hintergrund_wechsel = models.PositiveSmallIntegerField(
        "Hintergrundbilder wechseln alle … Sekunden", default=60,
        validators=[MinValueValidator(10), MaxValueValidator(3600)],
        help_text="Gilt, wenn es mehrere Bilder gibt (unten „Weitere Bilder“): Sie blenden "
        "langsam ineinander über, beim nächsten Seitenaufruf geht es mit dem nächsten weiter.",
    )  # fmt: skip
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    laendervorwahl = models.CharField(
        "Ländervorwahl", max_length=4, default="49", blank=True,
        help_text="Für WhatsApp-Nachrichten: Vorwahl ohne „+“ oder „00“ (Deutschland 49, "
        "Österreich 43, Schweiz 41). Gilt für Handynummern, die mit 0 beginnen.",
    )  # fmt: skip
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
    papierkorb_tage = models.PositiveSmallIntegerField(
        "Papierkorb leeren nach", default=30,
        choices=[(30, "30 Tagen"), (60, "60 Tagen"), (90, "90 Tagen"), (365, "365 Tagen")],
        help_text="Gelöschte Daten liegen so lange im Papierkorb und lassen sich wiederherstellen; "
        "danach löscht bintafeln sie endgültig.",
    )  # fmt: skip
    installation = models.UUIDField(
        "Kennung dieser Installation", default=uuid.uuid4, editable=False
    )
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    # Update-Warnung (ADR 0084): für welches Sicherheitsupdate schon gemailt wurde und bis wann
    # der Hinweis auf neue Funktionen ausgeblendet ist
    update_gemeldet = models.CharField("Gemeldetes Sicherheitsupdate", max_length=200, blank=True)
    update_hinweis_bis = models.DateField("Hinweis auf neue Funktionen ausgeblendet bis",
                                          null=True, blank=True)  # fmt: skip

    # Rechtstexte der Tafel (ADR 0094): Datenschutz, Impressum, Einverständniserklärung als interner
    # Text (HTML möglich). Ist ein Text gesetzt, führt der Link im Antragsformular auf eine eigene
    # öffentliche Seite; sonst gilt der externe Link aus den Antrags-Einstellungen. Angezeigt wird
    # der Text immer über apps.core.html bereinigt (nh3, keine Skripte).
    RECHTSTEXTE = ("datenschutz", "impressum", "einverstaendnis")
    datenschutz_text = models.TextField("Datenschutzerklärung (Text, HTML möglich)", blank=True)
    impressum_text = models.TextField("Impressum (Text, HTML möglich)", blank=True)
    einverstaendnis_text = models.TextField(
        "Einverständniserklärung (Text, HTML möglich)", blank=True
    )

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
    def anmeldung_bilder(self) -> list[str]:
        """Adressen der Hintergrundbilder der Anmeldeseite, in der Reihenfolge des Wechsels."""
        erstes = [self.hintergrund_anmeldung.url] if self.hintergrund_anmeldung else []
        return erstes + Hintergrundbild.adressen(Hintergrundbild.Bereich.ANMELDUNG)

    @property
    def seiten_bilder(self) -> list[str]:
        """Bilder der übrigen Seiten; ohne eigene die der Anmeldeseite."""
        erstes = [self.hintergrund.url] if self.hintergrund else []
        eigene = erstes + Hintergrundbild.adressen(Hintergrundbild.Bereich.SEITEN)
        return eigene or self.anmeldung_bilder

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


class Hintergrundbild(models.Model):
    """Weitere Hintergrundbilder; sie wechseln mit dem ersten aus den Tafel-Einstellungen ab."""

    class Bereich(models.TextChoices):
        ANMELDUNG = "anmeldung", "Anmeldeseite"
        SEITEN = "seiten", "übrige Seiten"

    bereich = models.CharField("Für", max_length=10, choices=Bereich.choices)
    bild = models.ImageField("Bild", upload_to="oeffentlich/hintergrund/")
    reihenfolge = models.PositiveIntegerField("Reihenfolge", default=0)

    class Meta:
        ordering = ["bereich", "reihenfolge", "pk"]
        verbose_name = "Hintergrundbild"
        verbose_name_plural = "Hintergrundbilder"

    def __str__(self):
        return f"Hintergrundbild ({self.get_bereich_display()})"

    @classmethod
    def adressen(cls, bereich: str) -> list[str]:
        return [h.bild.url for h in cls.objects.filter(bereich=bereich)]


class BenachrichtigungsWahl(models.Model):
    """Wie oft eine Person eine Art von Benachrichtigung bekommt (ADR 0086); ohne Eintrag sofort."""

    benutzer = models.ForeignKey("konten.Benutzer", on_delete=models.CASCADE,
                                 related_name="benachrichtigungen")  # fmt: skip
    art = models.CharField("Art", max_length=50)
    haeufigkeit = models.CharField("Wie oft", max_length=20, default="sofort")

    class Meta:
        unique_together = [("benutzer", "art")]
        verbose_name = "Benachrichtigungs-Wahl"
        verbose_name_plural = "Benachrichtigungs-Wahlen"

    def __str__(self):
        return f"{self.benutzer}: {self.art} {self.haeufigkeit}"


class BenachrichtigungsZeit(models.Model):
    """Wann gesammelte Benachrichtigungen kommen: Uhrzeit (täglich) und Wochentag (wöchentlich)."""

    benutzer = models.OneToOneField("konten.Benutzer", on_delete=models.CASCADE,
                                    related_name="benachrichtigungszeit")  # fmt: skip
    uhrzeit = models.TimeField("Uhrzeit", default=dt.time(7, 0))
    wochentag = models.PositiveSmallIntegerField(
        "Wochentag", default=0, choices=[(0, "Montag"), (1, "Dienstag"), (2, "Mittwoch"),
                                         (3, "Donnerstag"), (4, "Freitag"), (5, "Samstag"),
                                         (6, "Sonntag")],
    )  # fmt: skip

    class Meta:
        verbose_name = "Zeit der Benachrichtigungen"
        verbose_name_plural = "Zeiten der Benachrichtigungen"

    def __str__(self):
        return f"{self.benutzer}: {self.uhrzeit:%H:%M}"

    @classmethod
    def fuer(cls, benutzer) -> "BenachrichtigungsZeit":
        return cls.objects.filter(benutzer=benutzer).first() or cls(benutzer=benutzer)


class Meldung(models.Model):
    """Gesammelte Benachrichtigung, die auf ihren Versand wartet; danach gelöscht."""

    benutzer = models.ForeignKey("konten.Benutzer", on_delete=models.CASCADE,
                                 related_name="wartende_meldungen")  # fmt: skip
    art = models.CharField("Art", max_length=50)
    betreff = models.CharField("Betreff", max_length=200)
    text = models.TextField("Text")
    schluessel = models.CharField("Bezug", max_length=100, blank=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)
    faellig_am = models.DateTimeField("Versand ab")

    class Meta:
        verbose_name = "wartende Benachrichtigung"
        verbose_name_plural = "wartende Benachrichtigungen"

    def __str__(self):
        return f"{self.art}: {self.betreff}"


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


class FotoEinstellungen(models.Model):
    """Wie stark hochgeladene Fotos verkleinert werden (Singleton, ADR 0064): Quittungen,
    Dokumente, Belege, Führerscheinkopien, Anhänge von Anträgen. PDFs bleiben unverändert."""

    EINZIGE_ID = 1
    KANTEN = [(0, "nicht verkleinern (Original)"), (1000, "1000 Pixel – sehr klein"),
              (1280, "1280 Pixel – klein"), (1600, "1600 Pixel – gut lesbar (empfohlen)"),
              (2000, "2000 Pixel – groß"), (2560, "2560 Pixel – sehr groß")]  # fmt: skip

    kante = models.PositiveIntegerField(
        "Größe (längste Seite)", choices=KANTEN, default=1600,
        help_text="Handyfotos haben meist 4000 Pixel und 3–5 MB; mit 1600 Pixel sind Quittungen "
        "und Bescheide gut lesbar und etwa ein Zehntel so groß.",
    )  # fmt: skip
    qualitaet = models.PositiveSmallIntegerField(
        "Qualität (%)", default=75, validators=[MinValueValidator(40), MaxValueValidator(95)],
        help_text="Für JPEG und WebP. 75 ist ein guter Mittelweg; kleiner = kleinere Dateien, "
        "aber eher unscharf.",
    )  # fmt: skip
    graustufen = models.BooleanField(
        "In Graustufen speichern", default=False,
        help_text="Spart noch einmal Platz; Farben (z. B. Stempel) gehen verloren.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Foto-Einstellungen"
        verbose_name_plural = "Foto-Einstellungen"

    def __str__(self):
        return "Foto-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "FotoEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


auditlog.register(TafelEinstellungen, exclude_fields=["geaendert_am"])
auditlog.register(
    SicherungsAuftrag,
    include_fields=["name", "ziel", "aktiv", "wochentage", "uhrzeit", "anzahl", "tage",
                    "angefordert_am", "angefordert_von"],
)  # fmt: skip
# Das (verschlüsselte) Passwort gehört nicht ins Änderungsprotokoll.
auditlog.register(MailEinstellungen, exclude_fields=["passwort_verschluesselt"])
auditlog.register(FotoEinstellungen)


class PapierkorbEintrag(models.Model):
    """Etwas Gelöschtes mit allem, was mit ihm gelöscht wurde (ADR 0073, ``apps.core.papierkorb``).

    Nicht im Änderungsprotokoll registriert: Das Löschen und Wiederherstellen der Daten selbst
    steht dort schon, und eine Kopie der Inhalte im Protokoll bliebe nach dem Leeren übrig."""

    art = models.CharField("Art", max_length=100)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    recht = models.CharField("Recht", max_length=100, help_text="Wer es sehen und wiederherstellen "
                             "darf: dasselbe Recht wie zum Löschen.")  # fmt: skip
    kundennummer = models.CharField("Kundennummer", max_length=50, blank=True)
    stelle_id = models.IntegerField("Ausgabestelle", null=True, blank=True)
    geloescht_am = models.DateTimeField("Gelöscht am", auto_now_add=True)
    geloescht_von = models.CharField("Gelöscht von", max_length=150, blank=True)
    daten = models.JSONField("Daten", default=list)
    verweise = models.JSONField("Verweise", default=list, help_text="Felder anderer Datensätze, "
                                "die beim Löschen geleert wurden.")  # fmt: skip
    dateien = models.JSONField("Verschlüsselte Dateien", default=list)

    class Meta:
        verbose_name = "Eintrag im Papierkorb"
        verbose_name_plural = "Papierkorb"
        ordering = ["-geloescht_am", "-pk"]

    def __str__(self):
        return f"{self.art}: {self.bezeichnung}"


class VerzeichnisMeldung(models.Model):
    """Freiwillige Meldung dieser Installation im bintafeln-Verzeichnis (Singleton, ADR 0089).
    Gemeldet werden nur Name der Tafel, Kontakt-Mail und Version, nie Kunden- oder Personendaten."""

    EINZIGE_ID = 1

    aktiv = models.BooleanField("Diese Tafel im bintafeln-Verzeichnis melden", default=False)
    kontakt = models.EmailField(
        "Kontakt-Mail für Sicherheitshinweise", blank=True,
        help_text="Über diese Adresse erreicht der Herausgeber von bintafeln die Tafel, z. B. bei "
        "einer Sicherheitslücke. Leer = E-Mail der Tafel aus den Einstellungen.",
    )  # fmt: skip
    kennung = models.UUIDField(default=uuid.uuid4, editable=False)
    gemeldet_am = models.DateTimeField(null=True, blank=True, editable=False)
    gemeldete_version = models.CharField(max_length=50, blank=True, editable=False)
    fehler = models.CharField(max_length=300, blank=True, editable=False)

    class Meta:
        verbose_name = "Meldung im bintafeln-Verzeichnis"
        verbose_name_plural = "Meldung im bintafeln-Verzeichnis"

    def __str__(self):
        return "Meldung im bintafeln-Verzeichnis"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "VerzeichnisMeldung":
        meldung, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return meldung


class VerzeichnisEintrag(models.Model):
    """Gemeldete Tafel; nur auf der Installation des Herausgebers (VERZEICHNIS_EMPFANG)."""

    kennung = models.UUIDField(unique=True)
    name = models.CharField("Tafel", max_length=200)
    kontakt = models.EmailField("Kontakt", blank=True)
    version = models.CharField("Version", max_length=50, blank=True)
    erste_meldung = models.DateTimeField("Erste Meldung", auto_now_add=True)
    letzte_meldung = models.DateTimeField("Letzte Meldung", default=timezone.now)

    class Meta:
        ordering = ["name"]
        verbose_name = "Eintrag im bintafeln-Verzeichnis"
        verbose_name_plural = "Einträge im bintafeln-Verzeichnis"

    def __str__(self):
        return self.name
