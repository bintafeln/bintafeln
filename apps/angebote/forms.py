from django import forms

from apps.angebote.models import Angebot
from apps.konten.forms import DatumEingabe


class AngebotForm(forms.ModelForm):
    class Meta:
        model = Angebot
        fields = ["bezeichnung", "beschreibung", "anmeldung_von", "anmeldung_bis", "plaetze",
                  "hoechstens", "endet_am", "loeschen_nach_tagen"]  # fmt: skip
        widgets = {
            "anmeldung_von": DatumEingabe(), "anmeldung_bis": DatumEingabe(),
            "endet_am": DatumEingabe(), "beschreibung": forms.Textarea(attrs={"rows": 3}),
        }  # fmt: skip
