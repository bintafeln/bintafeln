"""Aufruf (Modul, ADR 0049/0050): Kundennummern der Reihe nach aufrufen, Monitor und Kiosk.

Die Reihenfolge eines Tages entsteht aus dem Kundenstamm (Kundengruppen der Ausgabestelle, die
heute dran sind) und liegt als JSON in ``AufrufTag.stand``; Regeln in ``apps/aufruf/ablauf.py``.
"""

import secrets

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.kunden.models import Ausgabestelle, AusgabestelleZeit, Zusatzfeld

TAGE = AusgabestelleZeit.Wochentag.choices

# Aufteilung und Schriftgrößen des Monitors (wie im bisherigen Aufrufsystem)
LAYOUT_STANDARD = {
    "next_customers_width": 15,
    "current_numbers_width": 40,
    "info_display_width": 45,
    "header_height": 120,
    "header_font": 2.8,
    "next_customers_font": 1.2,
    "current_numbers_font": 3.5,
    "info_display_font": 1.4,
}
# (kleinster, größter Wert); Breiten werden zusätzlich auf 100 % gebracht
LAYOUT_GRENZEN = {
    "next_customers_width": (10, 30),
    "current_numbers_width": (30, 60),
    "info_display_width": (20, 60),
    "header_height": (80, 200),
    "header_font": (1.5, 4.0),
    "next_customers_font": (0.8, 5.0),
    "current_numbers_font": (2.0, 15.0),
    "info_display_font": (0.8, 2.5),
}


def neuer_schluessel() -> str:
    return secrets.token_urlsafe(24)


class AufrufEinstellungen(models.Model):
    """Einstellungen des Aufrufs je Ausgabestelle, mit dem Schlüssel für die Anzeige-Geräte."""

    ausgabestelle = models.OneToOneField(Ausgabestelle, on_delete=models.CASCADE,
                                         related_name="aufruf")  # fmt: skip
    aktiv = models.BooleanField(
        "Aufruf an dieser Ausgabestelle", default=True,
        help_text="Aus: Diese Ausgabestelle ruft keine Nummern auf – kein Kasten „Aufruf“ unter "
        "dem Menü, keine Steuerung und keine Aufruf-Hinweise am Einlass.",
    )  # fmt: skip
    schluessel = models.CharField(
        "Schlüssel der Anzeige-Links", max_length=64, unique=True, default=neuer_schluessel,
        help_text="Steckt in den Links für Monitor, Anzeige und Kiosk. Neu erzeugen macht alte "
        "Links ungültig.",
    )  # fmt: skip
    anzahl = models.PositiveSmallIntegerField(
        "Nummern je Aufruf", default=3, validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="So viele Kundennummern erscheinen gleichzeitig mit „Bitte eintreten“.",
    )  # fmt: skip
    vorrang_feld = models.ForeignKey(
        Zusatzfeld, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Vorrang für", limit_choices_to={"typ": Zusatzfeld.Typ.JA_NEIN},
        help_text="Haushalte, bei denen dieses Ja/Nein-Feld (beim Haushalt oder bei einer Person) "
        "„ja“ ist, kommen in ihrer Gruppe zuerst – untereinander zufällig.",
    )  # fmt: skip
    vorrang_symbol = models.BooleanField(
        "Vorrang mit ♿ anzeigen", default=True,
        help_text="Zeigt das Symbol neben der Nummer auf Monitor und Steuerung. Achtung: Wer die "
        "Kundennummer kennt, sieht damit, dass der Haushalt Vorrang hat.",
    )  # fmt: skip
    eingelassene_ausblenden = models.BooleanField(
        "Schon Eingelassene herausnehmen", default=True,
        help_text="Haushalte, für die heute schon eine Abholung gebucht ist (z. B. mit Ausnahme "
        "vorgezogen), verschwinden aus der Warteschlange.",
    )  # fmt: skip
    spaetzuender_versatz = models.PositiveSmallIntegerField(
        "Zu spät Gekommene: Plätze nach hinten", default=30,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text="Wer schon aufgerufen war und später kommt, wird so viele wartende Plätze "
        "hinter der aktuellen Position neu einsortiert.",
    )  # fmt: skip
    zu_spaet_minuten = models.PositiveSmallIntegerField(
        "Am Einlass „zu spät“ nach (Minuten)", default=15, validators=[MaxValueValidator(600)],
        help_text="Kommt ein Kunde so viele Minuten nach seinem Aufruf zum Einlass, zeigt die "
        "Einlass-Karte „Zu spät“. 0 = nie.",
    )  # fmt: skip
    wochentag_probe = models.PositiveSmallIntegerField(
        "Probelauf als Wochentag", null=True, blank=True, choices=TAGE,
        help_text="Nur zum Ausprobieren: Der Aufruf nimmt die Kundengruppen dieses Wochentags. "
        "Danach wieder leeren.",
    )  # fmt: skip
    info_rotation = models.BooleanField("Infos auf dem Monitor zeigen", default=True)
    layout = models.JSONField("Monitor-Aufteilung", default=dict, blank=True)

    class Meta:
        verbose_name = "Aufruf-Einstellungen"
        verbose_name_plural = "Aufruf-Einstellungen"

    def __str__(self):
        return f"Aufruf {self.ausgabestelle}"

    @classmethod
    def laden(cls, stelle: Ausgabestelle) -> "AufrufEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(ausgabestelle=stelle)
        return einstellungen

    def layout_werte(self) -> dict:
        return {**LAYOUT_STANDARD, **{k: v for k, v in (self.layout or {}).items()
                                      if k in LAYOUT_STANDARD}}  # fmt: skip


class AufrufTag(models.Model):
    """Reihenfolge eines Tages an einer Ausgabestelle (vorübergehend, nach 4 Wochen gelöscht).

    ``stand``: {"gruppen": [{"pk", "name", "zeit", "wartend": [...], "aufgerufen": [...],
    "eingelassen": [...]}], "index": 0, "rueckgaengig": [...], "spaetzuender": {nr: {...}},
    "vorrang": [...]}. Enthält nur Kundennummern, keine Namen.
    """

    ausgabestelle = models.ForeignKey(Ausgabestelle, on_delete=models.CASCADE,
                                      related_name="aufruf_tage")  # fmt: skip
    datum = models.DateField("Datum")
    gestartet_am = models.DateTimeField("Gestartet am", null=True, blank=True)
    stand = models.JSONField("Stand", default=dict)
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        verbose_name = "Aufruf-Tag"
        verbose_name_plural = "Aufruf-Tage"
        constraints = [
            models.UniqueConstraint(fields=["ausgabestelle", "datum"], name="aufruftag_eindeutig")
        ]

    def __str__(self):
        return f"Aufruf {self.ausgabestelle} {self.datum:%d.%m.%Y}"


class KioskMeldung(models.Model):
    """Kundennummer heute am Kiosk gescannt: Der Kunde ist vermutlich schon da.

    Nur für den laufenden Tag; ältere Meldungen löscht ``ablauf`` beim nächsten Tag."""

    ausgabestelle = models.ForeignKey(Ausgabestelle, on_delete=models.CASCADE, related_name="+")
    datum = models.DateField("Datum")
    kundennummer = models.CharField("Kundennummer", max_length=20)
    zeitpunkt = models.DateTimeField("Gescannt um", auto_now_add=True)

    class Meta:
        verbose_name = "Meldung am Kiosk"
        verbose_name_plural = "Meldungen am Kiosk"
        constraints = [
            models.UniqueConstraint(
                fields=["ausgabestelle", "datum", "kundennummer"], name="kioskmeldung_eindeutig"
            )  # fmt: skip
        ]

    def __str__(self):
        return f"{self.kundennummer} am {self.datum:%d.%m.%Y}"


class AufrufInfo(models.Model):
    """Eine Info, die der Monitor im Wechsel neben den Nummern zeigt."""

    class Art(models.TextChoices):
        TEXT = "text", "Text"
        BILD = "bild", "Bild"
        PDF = "pdf", "PDF"
        WEBSEITE = "webseite", "Webseite"

    titel = models.CharField("Titel", max_length=100)
    art = models.CharField("Art", max_length=10, choices=Art.choices, default=Art.TEXT)
    text = models.TextField("Text", blank=True)
    datei = models.FileField(
        "Datei", upload_to="aufruf/", blank=True,
        help_text="Für Bild (JPG, PNG, WebP) oder PDF, höchstens 10 MB.",
    )  # fmt: skip
    adresse = models.URLField(
        "Adresse der Webseite", blank=True,
        help_text="Für Art Webseite, z. B. ein Wetter-Widget. Manche Seiten verbieten die Anzeige "
        "in fremden Seiten; dann bleibt die Fläche leer.",
    )  # fmt: skip
    dauer = models.PositiveSmallIntegerField(
        "Anzeigedauer (Sekunden)", default=10,
        validators=[MinValueValidator(3), MaxValueValidator(600)],
    )  # fmt: skip
    ausgabestellen = models.ManyToManyField(
        Ausgabestelle, blank=True, related_name="+", verbose_name="Nur an diesen Ausgabestellen",
        help_text="Keine Auswahl = an allen Ausgabestellen.",
    )  # fmt: skip
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Monitor-Info"
        verbose_name_plural = "Monitor-Infos"
        ordering = ["reihenfolge", "pk"]

    def __str__(self):
        return self.titel


auditlog.register(AufrufEinstellungen)
auditlog.register(AufrufInfo)
