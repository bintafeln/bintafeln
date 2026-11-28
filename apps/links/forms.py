from django import forms
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile

from apps.core import bilder, svg
from apps.core.forms import BildEingabe, Mehrfachauswahl
from apps.links.models import Link, LinkGruppe

BILD_MAX_BYTES = 2 * 1024 * 1024
BILD_KANTE = 480  # scharf genug für breite Logos, auch auf hochauflösenden Bildschirmen


class LinkForm(forms.ModelForm):
    class Meta:
        model = Link
        fields = ["titel", "untertitel", "beschreibung", "adresse", "symbol", "bild", "gruppe",
                  "warnung", "rollen", "neuer_tab", "reihenfolge", "aktiv"]  # fmt: skip
        widgets = {"bild": BildEingabe(attrs={"accept": "image/jpeg,image/png,image/webp,"
                                                      "image/svg+xml,.svg"}),
                   "rollen": Mehrfachauswahl(leer="alle Angemeldeten")}  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rollen"].queryset = Group.objects.filter(rolle__isnull=False).order_by("name")
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
