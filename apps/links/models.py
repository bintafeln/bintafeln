"""Links auf der Startseite (ADR 0057): Kacheln mit Gruppen, gepflegt in der Oberfläche."""

from urllib.parse import urlparse

from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.db import models


def adresse_pruefen(wert: str) -> None:
    """Nur http(s)-Adressen oder Pfade in bintafeln („/kunden/“), nie javascript: o. Ä."""
    if wert.startswith("/") and not wert.startswith("//"):
        return
    teile = urlparse(wert)
    if teile.scheme not in ("http", "https") or not teile.netloc:
        raise ValidationError("Bitte eine Adresse mit http:// oder https:// angeben oder einen "
                              "Pfad in bintafeln, der mit / beginnt.")  # fmt: skip


class LinkGruppe(models.Model):
    titel = models.CharField("Titel", max_length=100)
    reihenfolge = models.PositiveIntegerField("Reihenfolge", default=100)

    class Meta:
        verbose_name = "Linkgruppe"
        verbose_name_plural = "Linkgruppen"
        ordering = ["reihenfolge", "titel"]

    def __str__(self):
        return self.titel


class Link(models.Model):
    gruppe = models.ForeignKey(LinkGruppe, verbose_name="Gruppe", on_delete=models.SET_NULL,
                               null=True, blank=True, related_name="links")  # fmt: skip
    titel = models.CharField("Titel", max_length=100)
    untertitel = models.CharField("Untertitel", max_length=100, blank=True)
    beschreibung = models.CharField("Beschreibung", max_length=300, blank=True)
    adresse = models.CharField("Adresse", max_length=500, validators=[adresse_pruefen],
                               help_text="z. B. https://example.org oder /kunden/")  # fmt: skip
    symbol = models.CharField("Symbol", max_length=8, blank=True,
                              help_text="Ein Emoji, z. B. 📋 oder 🖥️.")  # fmt: skip
    bild = models.FileField(
        "Bild statt Symbol", upload_to="oeffentlich/links/", blank=True,
        help_text="PNG (auch mit transparentem Hintergrund), JPG, WebP oder SVG, höchstens 2 MB; "
        "ersetzt das Symbol. Öffentlich abrufbar.",
    )  # fmt: skip
    warnung = models.CharField(
        "Warnhinweis", max_length=200, blank=True,
        help_text="Rot hervorgehoben, z. B. „Nur für Admins – Änderungen wirken sofort“.",
    )  # fmt: skip
    recht = models.CharField(
        "Sichtbar für", max_length=60, blank=True,
        help_text="Leer = alle Angemeldeten; sonst nur, wer dieses Recht hat.",
    )  # fmt: skip
    neuer_tab = models.BooleanField("In neuem Tab öffnen", default=True)
    reihenfolge = models.PositiveIntegerField("Reihenfolge", default=100)
    aktiv = models.BooleanField("Aktiv", default=True)

    class Meta:
        verbose_name = "Link"
        verbose_name_plural = "Links"
        ordering = ["reihenfolge", "titel"]

    def __str__(self):
        return self.titel

    @property
    def ziel(self) -> str:
        """Kurz, wohin der Link führt (Rechnername oder Pfad)."""
        return urlparse(self.adresse).netloc or self.adresse


auditlog.register(LinkGruppe)
auditlog.register(Link)
