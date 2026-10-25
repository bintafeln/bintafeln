from django.db import models

from apps.kunden.models import Ausgabestelle


class WetterStand(models.Model):
    """Zuletzt abgerufenes Wetter je Ausgabestelle (Zwischenspeicher, ADR 0053).

    Vorübergehende Daten: nicht in der Datensicherung, jederzeit neu abrufbar.
    """

    ausgabestelle = models.OneToOneField(Ausgabestelle, on_delete=models.CASCADE, related_name="+")
    # „PLZ Ort“, für den die Koordinaten gelten; ändert sich die Anschrift, wird neu gesucht
    ort = models.CharField(max_length=120, blank=True)
    breite = models.FloatField(null=True, blank=True)
    laenge = models.FloatField(null=True, blank=True)
    temperatur = models.FloatField(null=True, blank=True)
    code = models.IntegerField("Wettercode (WMO)", null=True, blank=True)
    tag = models.BooleanField(default=True)
    abgerufen_am = models.DateTimeField(null=True, blank=True)
    fehler_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Wetterstand"
        verbose_name_plural = "Wetterstände"

    def __str__(self):
        return f"Wetter {self.ort}"
