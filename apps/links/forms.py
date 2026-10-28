from django import forms
from django.core.files.base import ContentFile

from apps.core import bilder, svg
from apps.core.auswahl import mit_vorhandenem
from apps.core.forms import BildEingabe
from apps.links.models import Link, LinkGruppe

BILD_MAX_BYTES = 2 * 1024 * 1024
BILD_KANTE = 480  # scharf genug für breite Logos, auch auf hochauflösenden Bildschirmen


def recht_auswahl(wert: str = "") -> list:
    from apps.konten import rechte

    auswahl = [("", "alle Angemeldeten")]
    for bereich, liste in rechte.bereiche():
        auswahl.append((bereich, [(r.code, r.bezeichnung) for r in liste]))
    bekannt = {c for _, gruppe in auswahl[1:] for c, _ in gruppe}
    if wert and wert not in bekannt:
        auswahl = mit_vorhandenem(auswahl, wert)
    return auswahl


class LinkForm(forms.ModelForm):
    recht = forms.ChoiceField(
        label="Sichtbar für",
        required=False,
        help_text="Leer = alle Angemeldeten; sonst nur, wer dieses Recht hat.",
    )

    class Meta:
        model = Link
        fields = ["titel", "untertitel", "beschreibung", "adresse", "symbol", "bild", "gruppe",
                  "warnung", "recht", "neuer_tab", "reihenfolge", "aktiv"]  # fmt: skip
        widgets = {"bild": BildEingabe(attrs={"accept": "image/jpeg,image/png,image/webp,"
                                                      "image/svg+xml,.svg"})}  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recht"].choices = recht_auswahl(self.instance.recht)
        self.fields["gruppe"].empty_label = "– ohne Gruppe –"

    def clean_bild(self):
        bild = self.cleaned_data.get("bild")
        if not bild or not hasattr(bild, "content_type"):
            return bild  # unverändert oder entfernt
        if bild.size > BILD_MAX_BYTES:
            raise forms.ValidationError("Das Bild darf höchstens 2 MB groß sein.")
        if bild.name.lower().endswith(".svg"):
            # Nur Zeichenelemente bleiben, Skripte und fremde Verweise fallen weg
            sauber = svg.bereinigen(bild.read())
            if sauber is None:
                raise forms.ValidationError("Diese SVG-Datei lässt sich nicht lesen.")
            return ContentFile(sauber, name=f"{bild.name.rsplit('.', 1)[0]}.svg")
        klein = bilder.verkleinern(bild, BILD_KANTE, transparenz=True)
        if klein is None:
            raise forms.ValidationError("Bitte ein Bild als PNG, JPG, WebP oder SVG wählen.")
        return klein


class GruppeForm(forms.ModelForm):
    class Meta:
        model = LinkGruppe
        fields = ["titel", "reihenfolge"]
