"""Stationen der Abholtouren (ADR 0147): Märkte, Bäckereien, Lieferanten, Lager … mit allem,
was der Fahrdienst an der Station braucht.

Die Stationen sind eine eigene Liste, nicht das Adressbuch: Sie kommen gesammelt per CSV aus dem
bisherigen System (``importieren.py``, Erkennung über ``kennung``) und tragen Angaben, die im
Adressbuch keinen Platz haben (Abholtage, Anfahrt, Adresse für Lieferscheine). Eine Station lässt
sich einmalig ins Adressbuch übertragen; danach zeigt ``adresse`` auf den Eintrag dort.
"""

from urllib.parse import urlencode

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core import zeichen

GOOGLE_MAPS_SUCHE = "https://www.google.com/maps/search/?"
GOOGLE_MAPS_ROUTE = "https://www.google.com/maps/dir/?"


class Station(models.Model):
    class Art(models.TextChoices):
        MARKT = "markt", "Markt"
        BAECKEREI = "baeckerei", "Bäckerei"
        LIEFERANT = "lieferant", "Lieferant"
        LAGER = "lager", "Lager"
        AUSGABESTELLE = "ausgabestelle", "Ausgabestelle"
        EINRICHTUNG = "einrichtung", "Einrichtung"
        SONSTIGES = "sonstiges", "Sonstiges"

    kennung = models.CharField(
        "Kennung", max_length=60, unique=True,
        help_text="Eindeutig und dauerhaft, z. B. die Nummer aus dem bisherigen System. Daran "
        "erkennt der Import, ob eine Station neu ist oder aktualisiert wird.",
    )  # fmt: skip
    art = models.CharField("Art", max_length=15, choices=Art.choices, default=Art.MARKT)
    name = models.CharField("Name", max_length=150, help_text="z. B. „Supermarkt Hauptstraße“")
    kette = models.CharField(
        "Kette", max_length=80, blank=True,
        help_text="z. B. der Name der Supermarktkette oder Bäckerei",
    )  # fmt: skip
    filialnummer = models.CharField("Filialnummer", max_length=40, blank=True)
    strasse = models.CharField("Straße", max_length=150)
    hausnummer = models.CharField("Hausnummer", max_length=20, blank=True)
    plz = models.CharField("PLZ", max_length=10)
    ort = models.CharField("Ort", max_length=100)
    ortsteil = models.CharField("Ortsteil", max_length=100, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    email_lieferschein = models.EmailField(
        "E-Mail für Lieferscheine", blank=True,
        help_text="Leer = die E-Mail darüber.",
    )  # fmt: skip
    ansprechpartner = models.CharField(
        "Ansprechpartner", max_length=150, blank=True,
        help_text="Geschäftlicher Kontakt in der Station, z. B. „Frau Muster, Marktleitung“.",
    )  # fmt: skip
    oeffnungszeiten = models.CharField("Öffnungszeiten", max_length=200, blank=True)
    abholtage = models.CharField("Abholtage", max_length=40, blank=True,
                                 help_text="An diesen Wochentagen wird abgeholt.")  # fmt: skip
    abholzeit = models.CharField("Abholzeit", max_length=150, blank=True,
                                 help_text="z. B. „ab 7:30, Rampe hinten“")  # fmt: skip
    anfahrt = models.TextField(
        "Anfahrt", blank=True,
        help_text="Für die Fahrer: Zufahrt, Rampe, Klingel, Parken.",
    )  # fmt: skip
    lieferschein = models.BooleanField(
        "Lieferschein", default=True,
        help_text="An dieser Station wird ein Lieferschein ausgefüllt.",
    )  # fmt: skip
    aktiv = models.BooleanField(
        "Aktiv", default=True,
        help_text="Ausschalten, wenn die Station nicht mehr angefahren wird.",
    )  # fmt: skip
    breite = models.DecimalField(
        "Breitengrad", max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        help_text="Nur nötig, wenn die Navigation die Anschrift nicht findet.",
    )  # fmt: skip
    laenge = models.DecimalField(
        "Längengrad", max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )  # fmt: skip
    notiz = models.TextField("Notiz", blank=True)
    adresse = models.OneToOneField(
        "adressen.Adresse", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="station", verbose_name="Eintrag im Adressbuch",
    )  # fmt: skip
    angelegt_am = models.DateTimeField("Angelegt am", auto_now_add=True)
    geaendert_am = models.DateTimeField("Geändert am", null=True, blank=True)
    geaendert_von = models.CharField("Geändert von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Station"
        verbose_name_plural = "Stationen"
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name

    TEXTFELDER = ("name", "kette", "strasse", "hausnummer", "plz", "ort", "ortsteil",
                  "ansprechpartner")  # fmt: skip

    def save(self, *args, **kwargs):
        # Text aus anderen Programmen: Ligaturen und unsichtbare Zeichen (wie Adresse.save)
        for feld in self.TEXTFELDER:
            setattr(self, feld, zeichen.bereinigen(getattr(self, feld)))
        super().save(*args, **kwargs)

    @property
    def strasse_hausnummer(self) -> str:
        return f"{self.strasse} {self.hausnummer}".strip()

    @property
    def anschrift(self) -> str:
        """Eine Zeile, z. B. für die Navigation: „Musterstraße 1, 12345 Musterstadt“."""
        return ", ".join(
            t for t in (self.strasse_hausnummer, f"{self.plz} {self.ort}".strip()) if t
        )

    @property
    def lieferschein_an(self) -> str:
        return self.email_lieferschein or self.email

    @property
    def ziel(self) -> str:
        """Ziel für Google Maps: Koordinaten, wenn eingetragen, sonst die Anschrift."""
        if self.breite is not None and self.laenge is not None:
            return f"{self.breite},{self.laenge}"
        return self.anschrift

    @property
    def navigation(self) -> str:
        """Link, der Google Maps mit der Route zur Station öffnet (am Handy die App, sonst die
        Webseite). Ohne API-Schlüssel; Daten gehen erst beim Antippen an Google."""
        return GOOGLE_MAPS_ROUTE + urlencode({"api": "1", "destination": self.ziel})

    @property
    def karte(self) -> str:
        """Link, der die Station in Google Maps zeigt (ohne Route)."""
        return GOOGLE_MAPS_SUCHE + urlencode({"api": "1", "query": self.ziel})


auditlog.register(Station)
