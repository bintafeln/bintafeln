"""Einstellungen des Bexat-Import-Moduls (ADR 0100).

Bexat kennt Ausgabestellen und Einkommensarten nur als Nummer. Die Namen stehen – soweit
vorhanden – im Export (Blatt ``offices``); die Einkommensarten sind je Tafel verschieden und
werden hier als Zuordnung (Nummer → Text) gepflegt. So bleiben keine festen, tafelspezifischen
Werte im Code.
"""

from django.db import models


def _nummer_text_lesen(text: str) -> dict:
    """Textfeld „Nummer = Text“ (eine Zuordnung je Zeile) → {Nummer: Text}."""
    zuordnung: dict[str, str] = {}
    for zeile in (text or "").splitlines():
        if "=" not in zeile:
            continue
        nummer, _, wert = zeile.partition("=")
        nummer, wert = nummer.strip(), wert.strip()
        if nummer.isdigit() and wert:
            zuordnung[nummer] = wert
    return zuordnung


def _nummer_text_schreiben(zuordnung: dict) -> str:
    """{Nummer: Text} → Textfeld, nach Nummer sortiert."""
    paare = sorted(((int(k), v) for k, v in (zuordnung or {}).items()), key=lambda p: p[0])
    return "\n".join(f"{k} = {v}" for k, v in paare)


class BexatEinstellungen(models.Model):
    """Zuordnungen für den Bexat-Import (Singleton)."""

    EINZIGE_ID = 1

    ausgabestellen = models.JSONField(
        "Ausgabestellen (Nummer → Name)",
        default=dict,
        blank=True,
        help_text="Nur nötig, wenn der Export die Ausgabestellen nicht selbst enthält. "
        "Eine Zuordnung je Zeile, z. B. „1 = Innenstadt“.",
    )
    einkommensarten = models.JSONField(
        "Einkommensarten (Nummer → Text)",
        default=dict,
        blank=True,
        help_text="Die Nummern stehen in der Bexat-Kundenkonfiguration. Eine Zuordnung je Zeile, "
        "z. B. „6 = Rente“. Ohne Eintrag bleibt die Einkommensart beim Import leer.",
    )

    class Meta:
        verbose_name = "Bexat-Einstellungen"
        verbose_name_plural = "Bexat-Einstellungen"

    def __str__(self):
        return "Bexat-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "BexatEinstellungen":
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen
