"""Stationen der Abholtouren (ADR 0147): Märkte, Bäckereien, Lieferanten, Lager … mit allem,
was der Fahrdienst an der Station braucht.

Die Stationen sind eine eigene Liste, nicht das Adressbuch: Sie kommen gesammelt per CSV aus dem
bisherigen System (``importieren.py``, Erkennung über ``kennung``) und tragen Angaben, die im
Adressbuch keinen Platz haben (Abholtage, Anfahrt, Adresse für Lieferscheine). Eine Station lässt
sich einmalig ins Adressbuch übertragen; danach zeigt ``adresse`` auf den Eintrag dort.
"""

from urllib.parse import urlencode

from auditlog.registry import auditlog
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core import zeichen

GOOGLE_MAPS_SUCHE = "https://www.google.com/maps/search/?"
GOOGLE_MAPS_ROUTE = "https://www.google.com/maps/dir/?"
GOOGLE_MAPS_KARTE = "https://www.google.com/maps/embed/v1/directions?"


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


class Tour(models.Model):
    """Eine Abholtour: Stationen in Fahrtreihenfolge (ADR 0148).

    Drei Arten, je nachdem, was gesetzt ist: mit ``fahrdienst_tour`` kommen Fahrtage und
    Besetzung aus dem Fahrerplan; ohne ist es eine eigene Tour mit eigenen Fahrtagen und
    Personen; mit ``datum`` eine kurzfristige Tour nur für diesen Tag.
    """

    name = models.CharField("Name", max_length=80, help_text="z. B. „Tour 3“ oder „Sonderfahrt“")
    fahrdienst_tour = models.ForeignKey(
        "fahrdienst.Tour", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="abholtouren", verbose_name="Tour im Fahrerplan",
        help_text="Dann kommen Fahrtage und Besetzung aus dem Fahrerplan. Leer = eigene Tour, "
        "die nicht im Fahrerplan steht.",
    )  # fmt: skip
    datum = models.DateField(
        "Nur am", null=True, blank=True,
        help_text="Kurzfristige Tour: fährt nur an diesem Tag.",
    )  # fmt: skip
    fahrtage = models.CharField(
        "Fahrtage", max_length=40, blank=True,
        help_text="Nichts angehakt = an jedem Tag (bei einer Tour aus dem Fahrerplan: an jedem "
        "Tag, an dem sie dort fährt). Angehakt z. B. nur „Mo“ für die Montags-Reihenfolge.",
    )  # fmt: skip
    personen = models.ManyToManyField(
        "adressen.Adresse", blank=True, related_name="abholtouren", verbose_name="Wer fährt",
        help_text="Für eigene und kurzfristige Touren. Bei einer Tour aus dem Fahrerplan steht "
        "die Besetzung dort.",
    )  # fmt: skip
    # Besetzung eigener und kurzfristiger Touren (ADR 0153): bis zu drei Personen und ein Gast.
    # ``personen`` bleibt die Menge aller, die mitfahren (Mail, „Ihre Tour“).
    fahrer = models.ForeignKey(
        "adressen.Adresse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Fahrer/in")  # fmt: skip
    beifahrer = models.ForeignKey(
        "adressen.Adresse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Beifahrer/in")  # fmt: skip
    beifahrer2 = models.ForeignKey(
        "adressen.Adresse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="2. Beifahrer/in")  # fmt: skip
    gast = models.CharField(
        "Gast", max_length=100, blank=True,
        help_text="Mitfahrer ohne eigenes Konto, z. B. Freiwillige, die einen Tag mitfahren.",
    )  # fmt: skip
    hinweis = models.TextField(
        "Für die Fahrer", blank=True,
        help_text="Steht oben auf der Tour, z. B. „Heute zuerst zum Lager“.",
    )  # fmt: skip
    aktiv = models.BooleanField("Aktiv", default=True)
    gesendet_am = models.DateTimeField("An die Fahrer geschickt am", null=True, blank=True)
    angelegt_am = models.DateTimeField("Angelegt am", auto_now_add=True)
    angelegt_von = models.CharField("Angelegt von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Abholtour"
        verbose_name_plural = "Abholtouren"
        ordering = ["datum", "name", "pk"]

    def __str__(self):
        return self.name

    @property
    def kurzfristig(self) -> bool:
        return self.datum is not None


class Tourstart(models.Model):
    """Die Besetzung einer Tour wurde an einem Tag am Handy bestätigt (ADR 0150)."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="starts")
    datum = models.DateField("Tag")
    bestaetigt_von = models.CharField("Bestätigt von", max_length=150)
    bestaetigt_am = models.DateTimeField("Bestätigt am", auto_now=True)
    geaendert = models.BooleanField("Besetzung dabei geändert", default=False)

    class Meta:
        verbose_name = "Tourstart"
        verbose_name_plural = "Tourstarts"
        constraints = [
            models.UniqueConstraint(fields=["tour", "datum"], name="touren_start_je_tag")
        ]

    def __str__(self):
        return f"{self.tour} am {self.datum:%d.%m.%Y}"


class Fahrzeug(models.Model):
    """Ein Fahrzeug der Tafel, zur Wahl beim Beginn einer Fahrt (ADR 0151)."""

    name = models.CharField("Name", max_length=60, unique=True,
                            help_text="z. B. „Kühlwagen“ oder „Transporter 2“")  # fmt: skip
    kennzeichen = models.CharField("Kennzeichen", max_length=15, blank=True)
    kilometerstand = models.PositiveIntegerField(
        "Kilometerstand", null=True, blank=True, validators=[MaxValueValidator(9_999_999)],
        help_text="Der aktuelle Stand. Er wird bei „Fahrt beginnen“ vorgeschlagen und mit jeder "
        "Fahrt fortgeschrieben; hier ändern, wenn das Fahrzeug anderweitig gefahren wurde.",
    )  # fmt: skip
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Fahrzeug"
        verbose_name_plural = "Fahrzeuge"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return f"{self.name} ({self.kennzeichen})" if self.kennzeichen else self.name


class Fahrt(models.Model):
    """Eine gefahrene Tour an einem Tag: Beginn und Ende mit Kilometerstand (ADR 0151). Namen
    stehen als Text dabei, damit die Fahrt lesbar bleibt, wenn Tour oder Fahrzeug verschwinden."""

    tour = models.ForeignKey(Tour, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="fahrten")  # fmt: skip
    tour_name = models.CharField("Tour", max_length=80)
    datum = models.DateField("Tag")
    fahrzeug = models.ForeignKey(Fahrzeug, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="fahrten", verbose_name="Fahrzeug")  # fmt: skip
    fahrzeug_name = models.CharField("Fahrzeug (Name)", max_length=80, blank=True)
    besetzung = models.CharField("Besetzung", max_length=300, blank=True)
    km_start = models.PositiveIntegerField(
        "Kilometerstand bei Abfahrt", validators=[MaxValueValidator(9_999_999)])  # fmt: skip
    km_ende = models.PositiveIntegerField(
        "Kilometerstand bei Ankunft", null=True, blank=True,
        validators=[MaxValueValidator(9_999_999)])  # fmt: skip
    begonnen_am = models.DateTimeField("Begonnen am")
    begonnen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+")  # fmt: skip
    begonnen_von_name = models.CharField("Begonnen von", max_length=150, blank=True)
    beendet_am = models.DateTimeField("Beendet am", null=True, blank=True)
    beendet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+")  # fmt: skip
    beendet_von_name = models.CharField("Beendet von", max_length=150, blank=True)
    berichtigt_von = models.CharField("Berichtigt von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Fahrt"
        verbose_name_plural = "Fahrten"
        ordering = ["-datum", "-begonnen_am"]
        constraints = [
            models.UniqueConstraint(fields=["tour", "datum"], name="touren_fahrt_je_tag")
        ]

    def __str__(self):
        return f"{self.tour_name} am {self.datum:%d.%m.%Y}"

    @property
    def km(self) -> int | None:
        """Gefahrene Kilometer – erst, wenn die Fahrt beendet ist."""
        return None if self.km_ende is None else self.km_ende - self.km_start

    @property
    def dauer(self):
        return self.beendet_am - self.begonnen_am if self.beendet_am else None


class Anfahrt(models.Model):
    """„Hier waren wir“: Die Station wurde an dem Tag auf der Tour angefahren (ADR 0152). Die
    Station bleibt in der Tour stehen – man fährt manchmal ein zweites Mal hin."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="anfahrten")
    station = models.ForeignKey("Station", on_delete=models.CASCADE, related_name="anfahrten")
    datum = models.DateField("Tag")
    am = models.DateTimeField("Angefahren am", auto_now_add=True)
    von = models.CharField("Eingetragen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Anfahrt"
        verbose_name_plural = "Anfahrten"
        constraints = [
            models.UniqueConstraint(
                fields=["tour", "station", "datum"], name="touren_anfahrt_je_tag"
            )  # fmt: skip
        ]

    def __str__(self):
        return f"{self.station} am {self.datum:%d.%m.%Y}"


class Fahrzeugmeldung(models.Model):
    """Was die Fahrer zum Fahrzeug melden (ADR 0155): Beanstandung („Lampe defekt“), „getankt“
    oder eine Anmerkung. Offene Meldungen sieht die Fahrdienstleitung auf ihrer Startseite."""

    class Art(models.TextChoices):
        MANGEL = "mangel", "Beanstandung / Defekt"
        GETANKT = "getankt", "Getankt"
        SONSTIGES = "sonstiges", "Anmerkung"

    fahrzeug = models.ForeignKey(Fahrzeug, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="meldungen")  # fmt: skip
    fahrzeug_name = models.CharField("Fahrzeug", max_length=80, blank=True)
    fahrt = models.ForeignKey(Fahrt, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="meldungen")  # fmt: skip
    tour_name = models.CharField("Tour", max_length=80, blank=True)
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.MANGEL)
    text = models.CharField("Meldung", max_length=500)
    gemeldet_am = models.DateTimeField("Gemeldet am", auto_now_add=True)
    gemeldet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+")  # fmt: skip
    gemeldet_von_name = models.CharField("Gemeldet von", max_length=150, blank=True)
    erledigt_am = models.DateTimeField("Erledigt am", null=True, blank=True)
    erledigt_von = models.CharField("Erledigt von", max_length=150, blank=True)
    erledigt_notiz = models.CharField("Was wurde getan?", max_length=300, blank=True)

    class Meta:
        verbose_name = "Meldung zum Fahrzeug"
        verbose_name_plural = "Meldungen zum Fahrzeug"
        ordering = ["-gemeldet_am"]

    def __str__(self):
        return f"{self.get_art_display()}: {self.text[:40]}"

    @property
    def offen(self) -> bool:
        return self.erledigt_am is None


class Zusatzstopp(models.Model):
    """Ein zusätzlicher Stopp einer Tour an einem Tag (ADR 0156): ein kurzfristiger
    Abholauftrag vom Büro oder von der Mannschaft selbst. Die feste Stationsfolge bleibt, wie
    sie ist."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="zusatzstopps")
    datum = models.DateField("Tag")
    station = models.ForeignKey("Station", on_delete=models.CASCADE, related_name="zusatzstopps")
    nach = models.PositiveSmallIntegerField(
        "Nach wie vielen Stationen", default=0,
        help_text="0 = ganz vorn; die Zahl der Stationen der Tour = am Ende.")  # fmt: skip
    hinweis = models.CharField("Was ist zu tun?", max_length=300, blank=True)
    angelegt_am = models.DateTimeField("Eingetragen am", auto_now_add=True)
    angelegt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+")  # fmt: skip
    angelegt_von_name = models.CharField("Eingetragen von", max_length=150, blank=True)
    # Vom Büro eingefügt (nicht von der Mannschaft selbst): Die Mannschaft bekommt eine Nachricht
    # und bestätigt, dass sie den Stopp gesehen hat (ADR 0159).
    vom_buero = models.BooleanField("Vom Büro eingefügt", default=False)
    gesehen_am = models.DateTimeField("Gesehen am", null=True, blank=True)
    gesehen_von_name = models.CharField("Gesehen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Zusatzstopp"
        verbose_name_plural = "Zusatzstopps"
        ordering = ["nach", "angelegt_am"]
        constraints = [
            models.UniqueConstraint(
                fields=["tour", "datum", "station"], name="touren_zusatzstopp_einmal"
            )  # fmt: skip
        ]

    def __str__(self):
        return f"{self.station} (Zusatzstopp {self.datum:%d.%m.%Y})"


class Halt(models.Model):
    """Eine Station auf einer Tour, an ihrer Stelle in der Fahrtreihenfolge."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="halte")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="halte")
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    wochentage = models.CharField(
        "Nur an diesen Tagen", max_length=40, blank=True,
        help_text="Leer = an allen Fahrtagen der Tour.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Halt"
        verbose_name_plural = "Halte"
        ordering = ["reihenfolge", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["tour", "station"], name="halt_station_einmal_je_tour")
        ]

    def __str__(self):
        return f"{self.tour}: {self.station}"


class TourenEinstellungen(models.Model):
    """Einstellungen des Moduls Touren (Singleton)."""

    EINZIGE_ID = 1

    class Versand(models.TextChoices):
        AUS = "aus", "ausgeschaltet – nur speichern"
        TEST = "test", "zum Test – nur an die Test-Adresse"
        AN = "an", "an die Station"

    lieferscheine = models.BooleanField(
        "Lieferscheine an den Stationen", default=True,
        help_text="Unterwegs lässt sich an jeder Station, bei der „Lieferschein“ eingeschaltet "
        "ist, ein Lieferschein ausfüllen und unterschreiben. In bintafeln bleibt er als PDF "
        "gespeichert.",
    )  # fmt: skip
    versand = models.CharField(
        "Lieferscheine per E-Mail verschicken", max_length=10, choices=Versand.choices,
        default=Versand.AUS,
        help_text="Ausgeschaltet: Lieferscheine werden nur gespeichert. Zum Test: Jeder "
        "Lieferschein geht nur an die Test-Adresse, keine Station bekommt Post. Später lassen "
        "sich gespeicherte Lieferscheine in der Liste nachsenden.",
    )  # fmt: skip
    test_email = models.EmailField(
        "Test-Adresse", blank=True,
        help_text="Im Testbetrieb gehen alle Lieferscheine hierhin statt an die Station.",
    )  # fmt: skip
    mail_text = models.TextField(
        "Text der E-Mail an die Station",
        default="Guten Tag,\n\nvielen Dank für Ihre Spende. Im Anhang finden Sie den "
        "Lieferschein zur heutigen Abholung.\n\nMit freundlichen Grüßen",
        help_text="Darunter steht automatisch der Name der Tafel.",
    )  # fmt: skip
    eco_plattform = models.BooleanField(
        "Wir arbeiten (auch) mit der ECO-Plattform", default=False,
        help_text="Dann steht bei den Touren ein Link zur ECO-Plattform. Touren, Stationen und "
        "Lieferscheine in bintafeln bleiben nutzbar.",
    )  # fmt: skip
    eco_adresse = models.URLField(
        "Adresse der ECO-Plattform", default="https://eco.tafel.de", blank=True)  # fmt: skip
    zentrale = models.CharField(
        "Start und Ziel der Touren (Zentrale)", max_length=200, blank=True,
        help_text="Anschrift, an der die Touren beginnen und enden, z. B. „Musterstraße 1, 12345 "
        "Musterstadt“. Leer = die Anschrift der Tafel. Sie ist Start und Ziel in der "
        "Routenvorschau der Planung und das letzte Ziel der Route am Handy.",
    )  # fmt: skip
    zentrale_aus = models.BooleanField(
        "Touren enden nicht an der Zentrale", default=False,
        help_text="Dann rechnet die Route nur von Station zu Station.",
    )  # fmt: skip
    karten_schluessel_verschluesselt = models.TextField(blank=True, editable=False)
    kiste_kg = models.DecimalField(
        "Durchschnittsgewicht einer Kiste (kg)", max_digits=5, decimal_places=1, default=10,
        validators=[MinValueValidator(0)],
        help_text="Damit rechnet die Statistik Kisten in Kilogramm um. Je Warengruppe lässt sich "
        "unten ein eigener Wert eintragen.",
    )  # fmt: skip
    aufbewahrung_jahre = models.PositiveSmallIntegerField(
        "Lieferscheine aufbewahren (Jahre)", default=10,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Danach werden sie automatisch gelöscht.",
    )  # fmt: skip
    naechste_nummer = models.PositiveIntegerField(
        "Nächste Lieferscheinnummer", default=1,
        help_text="Wird fortlaufend vergeben.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Touren-Einstellungen"
        verbose_name_plural = "Touren-Einstellungen"

    def __str__(self):
        return "Touren-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @property
    def start_ziel(self) -> str:
        """Anschrift der Zentrale für die Routen – leer, wenn Touren dort nicht enden oder
        keine Anschrift bekannt ist."""
        if self.zentrale_aus:
            return ""
        if self.zentrale.strip():
            return self.zentrale.strip()
        from apps.core.models import TafelEinstellungen

        return TafelEinstellungen.laden().anschrift

    @property
    def karten_schluessel(self) -> str:
        from apps.core import geheimnis

        if not self.karten_schluessel_verschluesselt:
            return ""
        return geheimnis.entschluesseln(self.karten_schluessel_verschluesselt) or ""

    @property
    def eco_link(self) -> str:
        """Adresse der ECO-Plattform, wenn die Tafel sie nutzt – sonst leer."""
        return self.eco_adresse if self.eco_plattform else ""

    @classmethod
    def laden(cls) -> "TourenEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


class Warengruppe(models.Model):
    """Zeile auf dem Lieferschein, z. B. „Obst/Gemüse“; die Tafel pflegt die Liste."""

    name = models.CharField("Name", max_length=60, unique=True)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    aktiv = models.BooleanField("Aktiv", default=True)
    kiste_kg = models.DecimalField(
        "kg je Kiste", max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text="Für die Statistik: Durchschnittsgewicht einer Kiste dieser Warengruppe. "
        "Leer = der allgemeine Wert.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Warengruppe"
        verbose_name_plural = "Warengruppen"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


class Lieferschein(models.Model):
    """Ein ausgefüllter und unterschriebener Lieferschein (ADR 0149).

    Das PDF wird einmal erzeugt und liegt verschlüsselt in ``datei``; es wird nie neu berechnet,
    die Unterschrift selbst wird deshalb nicht aufbewahrt. Name und Anschrift der Station und
    der Name der Tour sind festgehalten, wie sie beim Ausfüllen waren.
    """

    ORDNER = "lieferscheine"
    PRIVATDATEI = (ORDNER, "datei")

    nummer = models.PositiveIntegerField("Nummer", unique=True)
    station = models.ForeignKey(
        Station, null=True, blank=True, on_delete=models.SET_NULL, related_name="lieferscheine"
    )
    station_name = models.CharField("Station", max_length=150)
    station_anschrift = models.CharField("Anschrift", max_length=300, blank=True)
    tour = models.ForeignKey(
        Tour, null=True, blank=True, on_delete=models.SET_NULL, related_name="lieferscheine"
    )
    tour_name = models.CharField("Tour", max_length=80, blank=True)
    datum = models.DateField("Datum")
    anmerkung = models.TextField("Anmerkung", blank=True)
    datei = models.CharField(max_length=100, editable=False, blank=True)
    erstellt_von = models.ForeignKey(
        "konten.Benutzer", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    unterschrieben_von = models.CharField("Unterschrieben von", max_length=200)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)
    gesendet_an = models.CharField("Geschickt an", max_length=254, blank=True)
    gesendet_am = models.DateTimeField("Geschickt am", null=True, blank=True)
    mail_fehler = models.CharField("Nicht verschickt, weil", max_length=300, blank=True)

    class Meta:
        verbose_name = "Lieferschein"
        verbose_name_plural = "Lieferscheine"
        ordering = ["-nummer"]

    def __str__(self):
        return f"Lieferschein {self.nummer}"


class Position(models.Model):
    class Einheit(models.TextChoices):
        KISTEN = "kisten", "Kisten"
        KG = "kg", "kg"

    lieferschein = models.ForeignKey(Lieferschein, on_delete=models.CASCADE,
                                     related_name="positionen")  # fmt: skip
    warengruppe = models.CharField("Warengruppe", max_length=60)
    menge = models.DecimalField("Menge", max_digits=7, decimal_places=1)
    einheit = models.CharField("Einheit", max_length=10, choices=Einheit.choices,
                               default=Einheit.KISTEN)  # fmt: skip

    class Meta:
        verbose_name = "Position"
        verbose_name_plural = "Positionen"
        ordering = ["pk"]

    def __str__(self):
        return f"{self.warengruppe}: {self.menge_text}"

    @property
    def menge_text(self) -> str:
        zahl = f"{self.menge:.1f}".replace(".", ",").removesuffix(",0")
        return f"{zahl} {self.get_einheit_display()}"


auditlog.register(Tour, m2m_fields={"personen"})
auditlog.register(Halt)
auditlog.register(TourenEinstellungen, exclude_fields=["karten_schluessel_verschluesselt"])
auditlog.register(Warengruppe)
auditlog.register(Lieferschein)
auditlog.register(Fahrzeug)
auditlog.register(Fahrt)
auditlog.register(Fahrzeugmeldung)
auditlog.register(Zusatzstopp)
