"""Ausgabe (Modul 4): Einstellungen für Einlass und Ampel. Fachliche Grundlage:
docs/fachkonzept.md, Entscheidung: docs/adr/0013-empfang-erfasst-abholungen.md."""

from decimal import Decimal

from auditlog.registry import auditlog
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.kunden.models import Abholung, Ausgabestelle, Haushalt


def _betrag(name):
    return models.DecimalField(
        name,
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )


class AusgabeEinstellungen(models.Model):
    """Einstellungen der Ausgabe je Tafel (Singleton)."""

    EINZIGE_ID = 1

    class Zeitraum(models.TextChoices):
        WOCHE = "woche", "Kalenderwoche (Montag bis Sonntag)"
        VIERZEHN_TAGE = "14_tage", "14 Tage (heute und die 13 Tage davor)"
        MONAT = "monat", "Kalendermonat"

    max_je_tag = models.PositiveSmallIntegerField(
        "Höchstens … Abholungen am selben Tag",
        default=1,
        validators=[MaxValueValidator(20)],
        help_text="1 = einmal am Tag. 0 = beliebig oft (mehrfaches Abholen erlaubt).",
    )
    max_abholungen = models.PositiveSmallIntegerField(
        "Höchstens … Abholungen",
        default=1,
        validators=[MaxValueValidator(31)],
        help_text="0 = keine Höchstzahl je Zeitraum.",
    )
    zeitraum = models.CharField(
        "je Zeitraum", max_length=10, choices=Zeitraum.choices, default=Zeitraum.WOCHE
    )
    nicht_dran_rot = models.BooleanField(
        "„Heute nicht dran“ verhindert die Abholung",
        default=True,
        help_text="Ein: rot (nur mit Ausnahme). Aus: gelb, nur ein Hinweis.",
    )
    vorwarnung_tage = models.PositiveSmallIntegerField(
        "Vorwarnung vor Ablauf des Ausweises (Tage)",
        default=14,
        validators=[MaxValueValidator(365)],
    )
    zahlt_ab_alter = models.PositiveSmallIntegerField(
        "Beitrag zahlen Personen ab … Jahren",
        default=18,
        validators=[MaxValueValidator(99)],
        help_text="Personen ohne Geburtsdatum zahlen mit.",
    )
    beitrag_je_person = models.DecimalField(
        "Beitrag je zahlender Person (Euro)",
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.50"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    zusatzbeitraege = models.BooleanField(
        "Zusatzbeiträge berechnen",
        default=False,
        help_text="Nur wenn eingeschaltet, kommen die drei folgenden Beträge dazu.",
    )
    beitrag_je_abholung = _betrag("Zusatz: je Abholung (Euro)")
    beitrag_je_erwachsenem = _betrag("Zusatz: je Erwachsenem (Euro)")
    beitrag_je_kind = _betrag("Zusatz: je Kind (Euro)")
    kontostand_anzeigen = models.BooleanField("Kontostand am Einlass anzeigen", default=True)
    # Was der Einlass zeigt (je Tafel einstellbar, Fachkonzept Modul 4)
    einlass_haushaltsgroesse = models.BooleanField(
        "Einlass zeigt: Haushaltsgröße (Erwachsene/Kinder)", default=True
    )
    einlass_geburtsdaten = models.BooleanField(
        "Einlass zeigt: Geburtsdaten der Personen", default=True
    )
    einlass_abholer = models.BooleanField("Einlass zeigt: Abholberechtigte", default=True)
    einlass_anschrift = models.BooleanField(
        "Einlass zeigt: Anschrift",
        default=False,
        help_text="Nur einschalten, wenn der Einlass sie braucht (Datensparsamkeit).",
    )
    einlass_sperren = models.BooleanField(
        "Einlass zeigt: aktive Sperren mit Begründung",
        default=True,
        help_text="Aus: Die Ampel nennt nur „gesperrt“, ohne Begründung.",
    )
    einlass_abholungen = models.BooleanField("Einlass zeigt: letzte Abholungen", default=True)
    einlass_gruppenfarbe = models.BooleanField(
        "Einlass zeigt: Farbe der Kundengruppe", default=True
    )
    anschreiben_erlaubt = models.BooleanField(
        "Anschreiben erlauben",
        default=False,
        help_text="Abholung ohne Zahlung; der Kontostand darf dann negativ werden.",
    )
    buchungen_aufbewahren_jahre = models.PositiveSmallIntegerField(
        "Kontobuchungen aufbewahren (Jahre)",
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Für die Kasse. Nach Ablauf der Frist für Abholungen werden Buchungen "
        "anonymisiert (ohne Kundennummer), nach dieser Frist gelöscht. Bitte mit der "
        "Kassenführung des Vereins abstimmen.",
    )

    class Meta:
        verbose_name = "Einstellungen Ausgabe"
        verbose_name_plural = "Einstellungen Ausgabe"

    def __str__(self):
        return "Einstellungen Ausgabe"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "AusgabeEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen

    def beitrag(self, zahlende: int, erwachsene: int = 0, kinder: int = 0) -> Decimal:
        """Zahlende Personen × Beitrag; Zusatzbeiträge nur, wenn eingeschaltet."""
        summe = zahlende * self.beitrag_je_person
        if self.zusatzbeitraege:
            summe += (
                self.beitrag_je_abholung
                + erwachsene * self.beitrag_je_erwachsenem
                + kinder * self.beitrag_je_kind
            )
        return summe

    def beitrag_fuer(self, haushalt, heute, kind_bis_alter: int, frei_beachten=True) -> Decimal:
        """Beitrag eines Haushalts an einem Tag; in beitragsfreien Zeiträumen 0."""
        if frei_beachten and BeitragsfreierZeitraum.am(heute):
            return Decimal("0.00")
        zahlende, _ = haushalt.groesse(self.zahlt_ab_alter, heute)
        erwachsene, kinder = haushalt.groesse(kind_bis_alter, heute)
        return self.beitrag(zahlende, erwachsene, kinder)


class BeitragsfreierZeitraum(models.Model):
    """In diesem Zeitraum zahlen Kunden keinen Beitrag (z. B. vor Weihnachten)."""

    bezeichnung = models.CharField("Bezeichnung", max_length=100, help_text="z. B. Weihnachten")
    von = models.DateField("Von")
    bis = models.DateField("Bis einschließlich")

    class Meta:
        verbose_name = "Beitragsfreier Zeitraum"
        verbose_name_plural = "Beitragsfreie Zeiträume"
        ordering = ["-von"]

    def __str__(self):
        return f"{self.bezeichnung}: {self.von:%d.%m.%Y} bis {self.bis:%d.%m.%Y}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.von and self.bis and self.bis < self.von:
            raise ValidationError({"bis": "„Bis“ darf nicht vor „Von“ liegen."})

    @property
    def aktiv(self) -> bool:
        """Für die Listenansicht: vergangene Zeiträume gelten als inaktiv."""
        return self.bis >= timezone.localdate()

    @classmethod
    def am(cls, tag) -> "BeitragsfreierZeitraum | None":
        return cls.objects.filter(von__lte=tag, bis__gte=tag).first()


auditlog.register(AusgabeEinstellungen)


class Buchung(models.Model):
    """Eine Buchung im Kundenkonto. Auswirkung auf den Kontostand: haben − soll.

    ``bar`` ist das dabei bar eingenommene Geld (für die Kasse). Die Buchung hängt zusätzlich an
    der Kundennummer, damit die Kasse einen Neuimport des Kundenstamms übersteht (ADR 0014).
    """

    class Art(models.TextChoices):
        ABHOLUNG = "abholung", "Abholung"
        EINZAHLUNG = "einzahlung", "Einzahlung"
        KORREKTUR = "korrektur", "Korrektur"

    class Zahlweise(models.TextChoices):
        GUTHABEN = "guthaben", "aus Guthaben, Rest bar"
        BAR = "bar", "alles bar"
        ANSCHREIBEN = "anschreiben", "anschreiben"

    haushalt = models.ForeignKey(
        Haushalt, null=True, blank=True, on_delete=models.SET_NULL, related_name="buchungen"
    )
    kundennummer = models.CharField("Kundennummer", max_length=20, blank=True)
    datum = models.DateField("Datum", default=timezone.localdate, db_index=True)
    zeitpunkt = models.DateTimeField("Zeitpunkt", default=timezone.now)
    art = models.CharField("Art", max_length=12, choices=Art.choices)
    zahlweise = models.CharField("Zahlweise", max_length=12, choices=Zahlweise.choices, blank=True)
    soll = models.DecimalField("Soll", max_digits=8, decimal_places=2, default=Decimal("0.00"))
    haben = models.DecimalField("Haben", max_digits=8, decimal_places=2, default=Decimal("0.00"))
    bar = models.DecimalField(
        "Bar eingenommen", max_digits=8, decimal_places=2, default=Decimal("0.00")
    )
    abholung = models.OneToOneField(
        Abholung, null=True, blank=True, on_delete=models.SET_NULL, related_name="buchung"
    )
    ausgabestelle = models.ForeignKey(
        Ausgabestelle, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    bemerkung = models.CharField("Anmerkung", max_length=200, blank=True)
    eingetragen_von = models.CharField("Eingetragen von", max_length=100, blank=True)

    class Meta:
        verbose_name = "Buchung"
        verbose_name_plural = "Buchungen"
        ordering = ["-zeitpunkt"]

    def __str__(self):
        return f"{self.get_art_display()} vom {self.datum:%d.%m.%Y}"

    @property
    def wirkung(self) -> Decimal:
        """Veränderung des Kontostands."""
        return self.haben - self.soll


auditlog.register(Buchung)

auditlog.register(BeitragsfreierZeitraum)


class Sonderaktion(models.Model):
    """Aktion neben der normalen Ausgabe, z. B. Gutscheine vor Weihnachten (ADR 0032)."""

    class Menge(models.TextChoices):
        EINMAL = "einmal", "einmal je Haushalt"
        JE_KIND = "je_kind", "einmal je Kind"
        JE_PERSON = "je_person", "einmal je Person"

    bezeichnung = models.CharField(
        "Bezeichnung", max_length=100, help_text="z. B. Weihnachtsgutschein"
    )
    von = models.DateField("Von")
    bis = models.DateField("Bis einschließlich")
    beschreibung = models.CharField(
        "Hinweis für den Einlass", max_length=300, blank=True,
        help_text="Erscheint am Einlass, z. B. „Gutschein nur gegen Unterschrift ausgeben“.",
    )  # fmt: skip
    menge = models.CharField(
        "Wie viel je Haushalt", max_length=10, choices=Menge.choices, default=Menge.EINMAL
    )
    nur_mit_kindern = models.BooleanField(
        "Nur Haushalte mit Kindern",
        default=False,
        help_text="Kinder bis zum Alter aus „Einstellungen → Kundenstamm → Kind bis“.",
    )

    class Meta:
        verbose_name = "Sonderaktion"
        verbose_name_plural = "Sonderaktionen"
        ordering = ["-von", "bezeichnung"]

    def __str__(self):
        return self.bezeichnung

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.von and self.bis and self.bis < self.von:
            raise ValidationError({"bis": "„Bis“ darf nicht vor „Von“ liegen."})

    def laeuft(self, tag) -> bool:
        return self.von <= tag <= self.bis


class SonderaktionAuswahl(models.Model):
    """Wahlmöglichkeit einer Sonderaktion, z. B. „Spielzeug“ oder „Kleidung“."""

    aktion = models.ForeignKey(Sonderaktion, on_delete=models.CASCADE, related_name="auswahl")
    bezeichnung = models.CharField("Bezeichnung", max_length=100)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)

    class Meta:
        verbose_name = "Auswahl einer Sonderaktion"
        verbose_name_plural = "Auswahl von Sonderaktionen"
        ordering = ["reihenfolge", "pk"]

    def __str__(self):
        return self.bezeichnung


class Teilnahme(models.Model):
    """Ein Haushalt hat bei einer Sonderaktion etwas erhalten. Hängt an der Kundennummer."""

    aktion = models.ForeignKey(Sonderaktion, on_delete=models.CASCADE, related_name="teilnahmen")
    kundennummer = models.CharField("Kundennummer", max_length=20, db_index=True)
    auswahl = models.ForeignKey(
        SonderaktionAuswahl, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="teilnahmen", verbose_name="Auswahl",
    )  # fmt: skip
    menge = models.PositiveSmallIntegerField("Menge", default=1)
    zeitpunkt = models.DateTimeField("Zeitpunkt", default=timezone.now)
    ausgabestelle = models.ForeignKey(
        Ausgabestelle, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    eingetragen_von = models.CharField("Eingetragen von", max_length=100, blank=True)

    class Meta:
        verbose_name = "Teilnahme"
        verbose_name_plural = "Teilnahmen"
        ordering = ["-zeitpunkt"]
        constraints = [
            models.UniqueConstraint(
                fields=["aktion", "kundennummer"], name="teilnahme_einmal_je_haushalt"
            )
        ]

    def __str__(self):
        return f"{self.aktion}: {self.kundennummer}"


auditlog.register(Sonderaktion)
auditlog.register(SonderaktionAuswahl)
auditlog.register(Teilnahme)
