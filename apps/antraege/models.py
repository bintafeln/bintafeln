"""Online-Anträge auf Anmeldung oder Verlängerung (Modul 3, ADR 0024).

Ein Antrag ist kein Kunde: Solange der Kundenstamm aus dem Altsystem kommt (ADR 0006), überträgt
das Büro angenommene Anträge dorthin. Die Warteliste wird außerhalb von bintafeln abgearbeitet;
bintafeln führt die Anträge nach Eingang und kann sie exportieren.
"""

import datetime as dt

from auditlog.context import disable_auditlog
from auditlog.registry import auditlog
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.antraege import sprachen
from apps.core.auswahl import gdb_text

ANHANG_ORDNER = "antraege"

# Einordnung der Ausweisprüfung je Antrag (ADR 0112)
AUSWEIS_BEFUND = [
    ("", "nicht geprüft"),
    ("abweichung", "Ausweis – Staatsangehörigkeit weicht ab"),
    ("passt", "Ausweis – passt"),
    ("amtsdokument", "Amtsdokument (Bescheid, kein Ausweis)"),
    ("unklar", "unklar – Nachweis da, nichts erkannt"),
    ("ohne", "kein Bild-/PDF-Nachweis"),
]


class Abfrage(models.TextChoices):
    AUS = "aus", "nicht abfragen"
    OPTIONAL = "optional", "abfragen, freiwillig"
    PFLICHT = "pflicht", "abfragen, Pflicht"


def _abfrage(name, standard=Abfrage.OPTIONAL):
    return models.CharField(name, max_length=10, choices=Abfrage.choices, default=standard)


class AntragEinstellungen(models.Model):
    """Einstellungen des öffentlichen Antragsformulars (Singleton)."""

    EINZIGE_ID = 1

    class Modus(models.TextChoices):
        BEIDES = "beides", "Neuanmeldung und Verlängerung"
        NEU = "neu", "nur Neuanmeldung"
        VERLAENGERUNG = "verlaengerung", "nur Verlängerung"

    class Gebiet(models.TextChoices):
        AUS = "aus", "nicht prüfen"
        HINWEIS = "hinweis", "annehmen, aber markieren"
        SPERREN = "sperren", "nicht annehmen"

    aktiv = models.BooleanField(
        "Online-Anträge annehmen",
        default=False,
        help_text="Erst einschalten, wenn Texte und Datenschutzerklärung stimmen.",
    )
    modus = models.CharField("Art der Anträge", max_length=15, choices=Modus.choices,
                             default=Modus.BEIDES)  # fmt: skip
    kundennummer = _abfrage("Kundennummer (nur bei Verlängerung)")
    anrede = _abfrage("Anrede")
    geburtsdatum = _abfrage("Geburtsdatum", Abfrage.PFLICHT)
    anschrift = _abfrage("Anschrift", Abfrage.PFLICHT)
    telefon = _abfrage("Telefon")
    email = _abfrage("E-Mail")
    familienstand = _abfrage("Familienstand", Abfrage.AUS)
    staatsangehoerigkeit = _abfrage("Staatsangehörigkeit", Abfrage.AUS)
    # Gesundheitsdaten (Art. 9 DSGVO): nur abfragen, wenn die Tafel es bewusst einschaltet
    behinderung = _abfrage("Behinderung (GdB) je Person", Abfrage.AUS)
    angehoerige = _abfrage("Weitere Personen im Haushalt")
    wochentage = _abfrage("Bevorzugte Wochentage")
    ausgabestelle = _abfrage("Bevorzugte Ausgabestelle")
    anhaenge = _abfrage("Nachweise hochladen")
    nachricht = _abfrage("Nachricht an die Tafel")
    # Einzugsgebiet: Anschrift gegen PLZ und Orte prüfen (apps/antraege/gebiet.py)
    gebiet_pruefen = models.CharField(
        "Anschrift prüfen (Einzugsgebiet)", max_length=10, choices=Gebiet.choices,
        default=Gebiet.AUS,
        help_text="Liegt die Anschrift nicht im Gebiet, wird der Antrag markiert oder gar nicht "
        "angenommen. Geprüft werden nur PLZ und Ort, nicht, ob es die Anschrift gibt.",
    )  # fmt: skip
    gebiet_plz = models.CharField(
        "Postleitzahlen im Gebiet", max_length=500, blank=True,
        help_text="Einzelne PLZ oder Bereiche, mit Komma getrennt, z. B. 45127-45359. Leer = "
        "PLZ nicht prüfen.",
    )  # fmt: skip
    gebiet_orte = models.CharField(
        "Orte im Gebiet", max_length=500, blank=True,
        help_text="Mit Komma getrennt, z. B. Essen. Ortsteile wie „Essen-Steele“ passen dazu. "
        "Leer = Ort nicht prüfen. Sind PLZ und Orte eingetragen, muss beides passen.",
    )  # fmt: skip
    gebiet_name = models.CharField(
        "Name des Gebiets", max_length=100, blank=True,
        help_text="Steht in der Meldung im Formular, z. B. „Essen“: „Wir nehmen nur Anträge "
        "aus Essen an.“",
    )  # fmt: skip
    datenschutz_url = models.URLField("Link zur Datenschutzerklärung", blank=True)
    # Pflicht-Häkchen vor dem Absenden; ist ein Link eingetragen, steht er darunter
    einwilligung_abfragen = models.BooleanField(
        "Häkchen „Ich bin einverstanden, dass die Tafel meine Angaben speichert …“", default=True
    )
    datenschutz_abfragen = models.BooleanField(
        "Häkchen „Ich habe die Datenschutzerklärung gelesen.“", default=True
    )
    einverstaendnis_abfragen = models.BooleanField(
        "Häkchen „Ich habe die Einverständniserklärung gelesen und bin einverstanden.“",
        default=True)  # fmt: skip
    voraussetzungen_abfragen = models.BooleanField(
        "Häkchen „Voraussetzungen gelesen“ (nur sinnvoll mit Link oben)", default=False
    )
    erklaerungen_abfragen = models.BooleanField(
        "Häkchen „Erklärungen gelesen“ (z. B. Flyer; nur mit Link oben sinnvoll)",
        default=False)  # fmt: skip
    impressum_url = models.URLField("Link zum Impressum", blank=True)
    # Lokale Ausweisprüfung (MRZ lesen, ADR 0107): ein Knopf je Nachweis-Foto, nichts automatisch.
    ausweis_pruefen = models.BooleanField(
        "Ausweis-Foto lokal per OCR prüfen (MRZ)", default=False,
        help_text="Zeigt bei Nachweis-Fotos einen Knopf, der die maschinenlesbare Zone (MRZ) eines "
        "Ausweises liest und Land/Staatsangehörigkeit als Hinweis anzeigt. Läuft lokal auf dem "
        "Server (Tesseract), ohne externen Dienst; nur nach Klick, nie automatisch.",
    )  # fmt: skip
    # Aufbau der Seite: mitgelieferte Teile ein-/ausblenden; eigene Bereiche je Sprache: AntragText
    kopf_zeigen = models.BooleanField(
        "Kopfzeile mit Logo und Name zeigen", default=True,
        help_text="Die Sprachwahl bleibt immer. Einen eigenen Kopfbereich gestalten Sie unter "
        "„Texte je Sprache“.",
    )  # fmt: skip
    ueberschrift_zeigen = models.BooleanField("Überschrift über dem Formular zeigen", default=True)
    fuss_zeigen = models.BooleanField(
        "Fußzeile mit Anschrift und Links zeigen", default=True,
        help_text="Einen eigenen Fußbereich gestalten Sie unter „Texte je Sprache“.",
    )  # fmt: skip
    erklaerungen_url = models.URLField(
        "Link zu Erklärungen", blank=True,
        help_text="z. B. Seite der Tafel zur Lebensmittelausgabe: wie sie abläuft, was sie kostet.",
    )  # fmt: skip
    voraussetzungen_url = models.URLField(
        "Link zu Voraussetzungen", blank=True,
        help_text="Seite der Tafel: wer berechtigt ist und welche Nachweise nötig sind.",
    )  # fmt: skip
    einverstaendnis_url = models.URLField(
        "Link zur Einverständniserklärung", blank=True,
        help_text="z. B. PDF der Tafel zum Ausdrucken und Unterschreiben (Einverständnis zur "
        "Verarbeitung der Daten).",
    )  # fmt: skip
    # Der interne Text zu Datenschutz, Impressum und Einverständnis liegt in den Tafel-Einstellungen
    # (ADR 0094); hier stehen nur noch die externen Links als Rückfallebene (oben).
    # API-Schlüssel für die KI-Übersetzung der eigenen Texte (ADR 0082), verschlüsselt (ADR 0016)
    ki_schluessel_verschluesselt = models.TextField("API-Schlüssel (verschlüsselt)", blank=True)
    eigenes_css = models.TextField(
        "Eigene Gestaltung (CSS)",
        blank=True,
        help_text="Nur für Kundige: zusätzliche CSS-Regeln für das öffentliche Formular, z. B. "
        ".antrag-kopf { text-align: center; }. Leer lassen für die Standardgestaltung.",
    )
    benachrichtigen = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="+",
        verbose_name="Bei neuen Anträgen benachrichtigen",
        help_text="Diese Mitarbeitenden erhalten eine Mail ohne persönliche Angaben, mit Link.",
    )
    erste_nummer = models.PositiveIntegerField(
        "Nächste Antragsnummer ab",
        default=1,
        help_text="Neue Anträge bekommen fortlaufende Nummern, mindestens ab dieser Zahl, z. B. "
        "4201, wenn bisher bis 4200 gezählt wurde.",
    )
    erledigt_nach_tagen = models.PositiveSmallIntegerField(
        "Unbearbeitete Anträge gelten nach … Tagen als erledigt",
        default=0,
        validators=[MaxValueValidator(3650)],
        help_text="0 = nie.",
    )
    papierkorb_nach_tagen = models.PositiveSmallIntegerField(
        "Abgeschlossene Anträge nach … Tagen in den Papierkorb",
        default=90,
        validators=[MinValueValidator(1), MaxValueValidator(3650)],
        help_text="Danach liegen sie im gemeinsamen Papierkorb und werden dort nach der "
        "Tafel-weiten Frist („Papierkorb leeren nach“) endgültig gelöscht.",
    )
    max_je_stunde = models.PositiveSmallIntegerField(
        "Anträge je Stunde und Internetanschluss",
        default=5,
        validators=[MaxValueValidator(1000)],
        help_text="Schutz gegen massenhaftes Absenden: so viele Anträge darf ein Internetanschluss "
        "(IP-Adresse) in einer Stunde senden, danach kommt „Bitte später noch einmal“. 0 = aus. "
        "Höher stellen, wenn viele Menschen am selben Gerät oder WLAN einen Antrag ausfüllen.",
    )

    FELDER = [
        "kundennummer", "anrede", "geburtsdatum", "anschrift", "telefon", "email",
        "familienstand", "staatsangehoerigkeit", "behinderung", "angehoerige", "wochentage",
        "ausgabestelle", "anhaenge", "nachricht",
    ]  # fmt: skip

    class Meta:
        verbose_name = "Einstellungen Anträge"
        verbose_name_plural = "Einstellungen Anträge"

    def __str__(self):
        return "Einstellungen Anträge"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "AntragEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    # Datenschutz, Impressum, Einverständnis: externer Link (hier) oder – als Rückfallebene, wenn
    # kein Link gesetzt ist – der interne Text aus den Tafel-Einstellungen (ADR 0094).
    def rechtslink(self, art: str, sprache: str) -> str:
        """Der externe Link, wenn einer eingetragen ist; sonst die interne Seite mit dem in den
        Tafel-Einstellungen hinterlegten Text; sonst leer."""
        from django.urls import reverse

        from apps.core.models import TafelEinstellungen

        url = (getattr(self, f"{art}_url", "") or "").strip()
        if url:
            return url
        if (getattr(TafelEinstellungen.laden(), f"{art}_text", "") or "").strip():
            return reverse("antrag:rechtstext", args=[sprache, art])
        return ""

    def rechtslinks(self, sprache: str) -> dict:
        from apps.core.models import TafelEinstellungen

        return {art: self.rechtslink(art, sprache) for art in TafelEinstellungen.RECHTSTEXTE}


def naechste_antragsnummer() -> int:
    """Nächste freie Antragsnummer: über der höchsten vergebenen, mindestens ab der Einstellung.

    Sperrt die Einstellungen-Zeile, damit zwei gleichzeitige Anträge nicht dieselbe Nummer
    bekommen (läuft innerhalb der Transaktion des Speicherns).
    """
    from django.db.models import Max

    e = AntragEinstellungen.objects.select_for_update().filter(pk=AntragEinstellungen.EINZIGE_ID)
    erste = e.values_list("erste_nummer", flat=True).first() or 1
    hoechste = Antrag.objects.aggregate(m=Max("laufnummer"))["m"] or 0
    return max(hoechste + 1, erste)


class AntragText(models.Model):
    """Eigene Texte der Tafel für eine Sprache; ohne Eintrag gelten die mitgelieferten."""

    sprache = models.CharField("Sprache", max_length=5, choices=sprachen.AUSWAHL, unique=True)
    ueberschrift = models.CharField("Überschrift", max_length=200, blank=True)
    einleitung = models.TextField("Einleitung (HTML möglich)", blank=True)
    bestaetigung = models.TextField("Seite nach dem Absenden (HTML möglich)", blank=True)
    mail_betreff = models.CharField("Betreff der Antwortmail", max_length=200, blank=True)
    mail_text = models.TextField("Antwortmail (HTML möglich)", blank=True)
    anhaenge_hinweis = models.TextField("Hinweis zu den Nachweisen (HTML möglich)", blank=True)
    kopf = models.TextField("Eigener Kopfbereich (HTML möglich)", blank=True)
    fuss = models.TextField("Eigener Fußbereich (HTML möglich)", blank=True)

    class Meta:
        verbose_name = "Text des Antragsformulars"
        verbose_name_plural = "Texte des Antragsformulars"
        ordering = ["sprache"]

    def __str__(self):
        return f"Texte {self.get_sprache_display()}"


class Antrag(models.Model):
    class Art(models.TextChoices):
        NEU = "neu", "Neuanmeldung"
        VERLAENGERUNG = "verlaengerung", "Verlängerung"

    class Status(models.TextChoices):
        NEU = "neu", "neu"
        IN_BEARBEITUNG = "in_bearbeitung", "in Bearbeitung"
        ERLEDIGT = "erledigt", "erledigt"
        ABGELEHNT = "abgelehnt", "abgelehnt"

    OFFEN = (Status.NEU, Status.IN_BEARBEITUNG)

    laufnummer = models.PositiveIntegerField("Antragsnummer", unique=True, null=True, blank=True)
    eingegangen_am = models.DateTimeField("Eingegangen am", default=timezone.now, db_index=True)
    art = models.CharField("Art", max_length=15, choices=Art.choices, default=Art.NEU)
    sprache = models.CharField("Sprache", max_length=5, choices=sprachen.AUSWAHL, default="de")
    status = models.CharField("Status", max_length=15, choices=Status.choices, default=Status.NEU)
    abgeschlossen_am = models.DateTimeField("Abgeschlossen am", null=True, blank=True)
    kundennummer = models.CharField("Kundennummer", max_length=20, blank=True)
    anrede = models.CharField("Anrede", max_length=30, blank=True)
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    familienstand = models.CharField("Familienstand", max_length=50, blank=True)
    staatsangehoerigkeit = models.CharField("Staatsangehörigkeit", max_length=100, blank=True)
    gdb = models.PositiveSmallIntegerField(
        "Grad der Behinderung", null=True, blank=True,
        help_text="0 = keine Behinderung, leer = keine Angabe.",
    )  # fmt: skip
    merkzeichen = models.CharField("Merkzeichen", max_length=60, blank=True)
    wochentage = models.CharField("Bevorzugte Wochentage", max_length=30, blank=True)
    # Beim Absenden bestätigt (Pflicht-Häkchen, wenn die Tafel den Link eingetragen hat)
    # Bisher war das Häkchen zum Speichern immer Pflicht, daher für alte Anträge „ja“
    einwilligung_bestaetigt = models.BooleanField("Speichern der Angaben bestätigt", default=True)
    datenschutz_bestaetigt = models.BooleanField("Datenschutzerklärung bestätigt", default=False)
    voraussetzungen_bestaetigt = models.BooleanField("Voraussetzungen bestätigt", default=False)
    erklaerungen_bestaetigt = models.BooleanField("Erklärungen bestätigt", default=False)
    einverstaendnis_bestaetigt = models.BooleanField("Einverständniserklärung bestätigt",
                                                     default=False)  # fmt: skip
    ausgabestelle = models.CharField("Bevorzugte Ausgabestelle", max_length=100, blank=True)
    nachricht = models.TextField("Nachricht", blank=True)
    bearbeitet_von = models.CharField("Zuletzt bearbeitet von", max_length=150, blank=True)
    # Ergebnis der lokalen Ausweisprüfung über alle Nachweise (ADR 0107): die im Ausweis erkannte
    # Staatsangehörigkeit, ob sie zu keiner angegebenen passt (Abweichung), und welches Foto es war.
    # Nur ein Hinweis; die Entscheidung trifft ein Mensch.
    ausweis_geprueft_am = models.DateTimeField(null=True, blank=True, editable=False)
    ausweis_staat = models.CharField(max_length=100, blank=True, editable=False)
    ausweis_abweichung = models.BooleanField(default=False, editable=False)
    ausweis_anhang = models.ForeignKey(
        "AntragAnhang", null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="+",
    )  # fmt: skip
    # Eine Person hat die Abweichung auf der Sammel-Prüfseite abgeschlossen (übernommen oder
    # bewusst nicht übernommen) – dann verschwindet sie aus der Liste der offenen Fälle (ADR 0107).
    ausweis_erledigt = models.BooleanField(default=False, editable=False)
    # Einordnung der Nachweise beim Scan (ADR 0112): Ausweis mit Abweichung, Ausweis passt,
    # Amtsdokument (Bescheid – kein Ausweis), unklar (Nachweis da, nichts erkannt) oder ohne
    # Nachweis. Trennt die „nichts erkannt“-Fälle, damit reine Bescheide nicht von Hand geprüft
    # werden müssen. Leer = (noch) nicht eingeordnet.
    ausweis_befund = models.CharField(
        max_length=20, blank=True, default="", editable=False, choices=AUSWEIS_BEFUND
    )

    class Meta:
        verbose_name = "Antrag"
        verbose_name_plural = "Anträge"
        ordering = ["eingegangen_am", "pk"]  # Reihenfolge nach Eingang

    def __str__(self):
        return f"Antrag {self.nummer}"

    def save(self, *args, **kwargs):
        if self.laufnummer:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            self.laufnummer = naechste_antragsnummer()
            super().save(*args, **kwargs)

    @property
    def gdb_text(self) -> str:
        return gdb_text(self.gdb, self.merkzeichen)

    @property
    def nummer(self) -> str:
        return str(self.laufnummer) if self.laufnummer else str(self.pk)

    @property
    def name(self) -> str:
        return f"{self.vorname} {self.nachname}"

    def status_setzen(self, status: str, von: str) -> None:
        self.status, self.bearbeitet_von = status, von
        self.abgeschlossen_am = None if status in self.OFFEN else timezone.now()
        self.save()


class AntragPerson(models.Model):
    """Weitere Person im Haushalt."""

    antrag = models.ForeignKey(Antrag, on_delete=models.CASCADE, related_name="personen")
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100, blank=True)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    staatsangehoerigkeit = models.CharField("Staatsangehörigkeit", max_length=100, blank=True)
    gdb = models.PositiveSmallIntegerField(
        "Grad der Behinderung", null=True, blank=True,
        help_text="0 = keine Behinderung, leer = keine Angabe.",
    )  # fmt: skip
    merkzeichen = models.CharField("Merkzeichen", max_length=60, blank=True)

    class Meta:
        verbose_name = "Person im Antrag"
        verbose_name_plural = "Personen im Antrag"
        ordering = ["pk"]

    def __str__(self):
        return f"{self.vorname} {self.nachname}".strip()

    @property
    def gdb_text(self) -> str:
        return gdb_text(self.gdb, self.merkzeichen)


class AntragAnhang(models.Model):
    """Verschlüsselt abgelegter Nachweis (apps.core.privatdateien)."""

    PRIVATDATEI = (ANHANG_ORDNER, "datei")  # Alle Dateien, Papierkorb (ADR 0073)
    DATEIEN_BEREICH = "Nachweise zu Anträgen"

    antrag = models.ForeignKey(Antrag, on_delete=models.CASCADE, related_name="anhaenge")
    name = models.CharField("Dateiname", max_length=200)
    datei = models.CharField(max_length=200, editable=False)
    typ = models.CharField(max_length=100, editable=False)
    groesse = models.PositiveIntegerField("Größe in Bytes", default=0)

    class Meta:
        verbose_name = "Nachweis"
        verbose_name_plural = "Nachweise"
        ordering = ["pk"]

    def __str__(self):
        return self.name


class AntragEntwurfNachweis(models.Model):
    """Ein schon hochgeladener Nachweis, der noch zu keinem Antrag gehört: Er wird beim Absenden
    verschlüsselt zwischengelegt und an die Sitzung gebunden, damit die Dateien bei einem
    Formularfehler nicht verloren gehen. Beim erfolgreichen Absenden werden daraus ``AntragAnhang``;
    liegen bleibende Entwürfe räumt ``fristen_anwenden`` nach einem Tag weg."""

    PRIVATDATEI = (ANHANG_ORDNER, "datei")

    sitzung = models.CharField(max_length=40, db_index=True)
    name = models.CharField("Dateiname", max_length=200)
    datei = models.CharField(max_length=200, editable=False)
    typ = models.CharField(max_length=100, editable=False)
    groesse = models.PositiveIntegerField("Größe in Bytes", default=0)
    erstellt_am = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Nachweis-Entwurf"
        verbose_name_plural = "Nachweis-Entwürfe"
        ordering = ["pk"]

    def __str__(self):
        return self.name


class AntragAnmerkung(models.Model):
    antrag = models.ForeignKey(Antrag, on_delete=models.CASCADE, related_name="anmerkungen")
    zeitpunkt = models.DateTimeField("Zeitpunkt", default=timezone.now)
    text = models.TextField("Anmerkung")
    von = models.CharField("Von", max_length=150)

    class Meta:
        verbose_name = "Anmerkung zum Antrag"
        verbose_name_plural = "Anmerkungen zu Anträgen"
        ordering = ["zeitpunkt"]

    def __str__(self):
        return f"Anmerkung vom {timezone.localtime(self.zeitpunkt):%d.%m.%Y}"


class AntragVersuch(models.Model):
    """Missbrauchsschutz: Absendeversuche je Adresse, nur als Prüfsumme, nach einem Tag weg."""

    schluessel = models.CharField(max_length=64, db_index=True)
    zeitpunkt = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Absendeversuch"
        verbose_name_plural = "Absendeversuche"

    def __str__(self):
        return f"Versuch {timezone.localtime(self.zeitpunkt):%d.%m.%Y %H:%M}"


auditlog.register(AntragEinstellungen, m2m_fields={"benachrichtigen"},
                  exclude_fields=["ki_schluessel_verschluesselt"])  # fmt: skip
auditlog.register(AntragText)
auditlog.register(Antrag, exclude_fields=[
    "ausweis_geprueft_am", "ausweis_staat", "ausweis_abweichung", "ausweis_anhang"])  # fmt: skip
auditlog.register(AntragPerson)
auditlog.register(AntragAnhang, exclude_fields=["datei"])
auditlog.register(AntragAnmerkung)


def in_papierkorb(antrag: Antrag, benutzer=None):
    """Legt einen Antrag mit allem, was daran hängt (Personen, Nachweise, Anmerkungen), in den
    gemeinsamen Papierkorb (ADR 0073). Von dort wiederherstellbar; die endgültige Löschung
    besorgt ``papierkorb.fristen_anwenden`` nach der Tafel-weiten Frist."""
    from apps.core import papierkorb

    return papierkorb.loeschen(
        benutzer, "Antrag", f"{antrag.nummer} · {antrag.name}", antrag,
        recht="antraege.loeschen", kundennummer=antrag.kundennummer)  # fmt: skip


def fristen_anwenden(jetzt=None) -> int:
    """Fristen der Anträge (ADR 0024); liefert die Zahl der in den Papierkorb gelegten.

    Unbearbeitete gelten nach N Tagen als erledigt (wenn eingestellt), abgeschlossene kommen
    nach N Tagen in den gemeinsamen Papierkorb (ADR 0073), wo sie nach der Tafel-weiten Frist
    endgültig gelöscht werden, samt Nachweisen. Absendeversuche (Missbrauchsschutz) bleiben
    einen Tag.
    """
    jetzt = jetzt or timezone.now()
    e = AntragEinstellungen.laden()
    tage = dt.timedelta
    AntragVersuch.objects.filter(zeitpunkt__lt=jetzt - tage(days=1)).delete()
    from apps.antraege import nachweise  # liegen gebliebene Nachweis-Entwürfe wegräumen

    nachweise.aufraeumen(jetzt)
    if e.erledigt_nach_tagen:
        Antrag.objects.filter(
            status__in=Antrag.OFFEN,
            eingegangen_am__lt=jetzt - tage(days=e.erledigt_nach_tagen),
        ).update(status=Antrag.Status.ERLEDIGT, abgeschlossen_am=jetzt, bearbeitet_von="Frist")
    faellig = list(Antrag.objects.filter(
        abgeschlossen_am__lt=jetzt - tage(days=e.papierkorb_nach_tagen)))  # fmt: skip
    for antrag in faellig:
        in_papierkorb(antrag)
    return len(faellig)


def loeschen(antrag: Antrag) -> None:
    """Löscht einen Antrag sofort und endgültig, mit verschlüsselten Nachweisen und
    Protokolleinträgen (für das Zurücksetzen der Demo-Daten; das normale Löschen läuft über
    ``in_papierkorb`` und den gemeinsamen Papierkorb)."""
    from auditlog.models import LogEntry
    from django.contrib.contenttypes.models import ContentType

    from apps.core import privatdateien

    for anhang in antrag.anhaenge.all():
        privatdateien.loeschen(ANHANG_ORDNER, anhang.datei)
    teile = [
        (Antrag, [antrag.pk]),
        (AntragPerson, list(antrag.personen.values_list("pk", flat=True))),
        (AntragAnhang, list(antrag.anhaenge.values_list("pk", flat=True))),
        (AntragAnmerkung, list(antrag.anmerkungen.values_list("pk", flat=True))),
    ]
    with disable_auditlog():
        antrag.delete()
    for modell, schluessel in teile:
        LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(modell),
            object_pk__in=[str(k) for k in schluessel],
        ).delete()
