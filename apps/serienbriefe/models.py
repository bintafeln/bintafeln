"""Serienbriefe (Modul 5, ADR 0047): Vorlagen mit Platzhaltern und vermerkte Versände."""

from auditlog.registry import auditlog
from django.db import models


class Vorlage(models.Model):
    name = models.CharField("Name", max_length=100, unique=True)
    betreff = models.CharField("Betreff", max_length=200)
    text = models.TextField(
        "Text",
        help_text="Gestalten wie in einem Schreibprogramm. Platzhalter aus der Liste "
        "„Platzhalter“ in den Text ziehen oder antippen (fügt sie an der Schreibmarke ein); "
        "im Reiter HTML stehen sie als {anrede}, {spendensumme} usw.",
    )
    briefkopf = models.BooleanField(
        "Briefkopf", default=True,
        help_text="Logo, Name, Anschrift und Kontakt der Tafel oben rechts (aus den "
        "Tafel-Einstellungen). Aus, wenn Sie auf eigenes Briefpapier drucken.",
    )  # fmt: skip
    fusszeile = models.TextField(
        "Fußzeile", blank=True,
        help_text="Steht unten auf jeder Seite des Briefs und unter jeder E-Mail, z. B. "
        "Bankverbindung, Vereinsregister, Vorstand. Leer = keine Fußzeile.",
    )  # fmt: skip
    freie_grafiken = models.JSONField(
        "Frei gesetzte Grafiken", default=list, blank=True,
        help_text="Grafiken an fester Stelle der Seite, z. B. Unterschriften (ADR 0166).",
    )  # fmt: skip
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        verbose_name = "Serienbrief-Vorlage"
        verbose_name_plural = "Serienbrief-Vorlagen"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Versand(models.Model):
    class Art(models.TextChoices):
        BRIEF = "brief", "Briefe (PDF)"
        EMAIL = "email", "E-Mail"

    am = models.DateTimeField("Am", auto_now_add=True)
    von = models.CharField("Von", max_length=150)
    art = models.CharField("Art", max_length=10, choices=Art.choices)
    vorlage = models.CharField("Vorlage", max_length=100)
    betreff = models.CharField("Betreff", max_length=200)
    auswahl = models.CharField("Empfänger", max_length=300)
    anzahl = models.PositiveIntegerField("Anzahl")
    empfaenger = models.JSONField(
        "Empfänger-Schlüssel", default=list,
        help_text="a:<Adresse> bzw. k:<Kundennummer>; für die Auskunft, wer was bekommen hat.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Serienbrief-Versand"
        verbose_name_plural = "Serienbrief-Versände"
        ordering = ["-am"]

    def __str__(self):
        return f"{self.betreff} ({self.am:%d.%m.%Y})"


class Grafik(models.Model):
    """Bild für Vorlagen (Logo, Foto, Unterschrift …), ADR 0138. Beim Hochladen neu gespeichert
    (``grafiken.speichern()``): verkleinert und ohne Metadaten wie Ort oder Kamera."""

    name = models.CharField("Name", max_length=150)
    bild = models.ImageField("Bild", upload_to="serienbriefe/grafiken/")
    breite = models.PositiveIntegerField("Breite (Pixel)")
    hoehe = models.PositiveIntegerField("Höhe (Pixel)")
    hochgeladen_am = models.DateTimeField("Hochgeladen am", auto_now_add=True)
    hochgeladen_von = models.CharField("Hochgeladen von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Grafik für Serienbriefe"
        verbose_name_plural = "Grafiken für Serienbriefe"
        ordering = ["-hochgeladen_am"]

    def __str__(self):
        return self.name


auditlog.register(Vorlage, exclude_fields=["geaendert_am"])
