from django import forms

from apps.aushang.models import Aushang, AushangSeite


class AushangForm(forms.ModelForm):
    class Meta:
        model = Aushang
        fields = ["name", "aktiv", "nebeneinander", "sekunden"]


class NeuForm(forms.ModelForm):
    class Meta:
        model = Aushang
        fields = ["name"]


class SeiteForm(forms.Form):
    seite = forms.ChoiceField(label="Seite")
    monate = forms.TypedChoiceField(label="Zeitraum", choices=AushangSeite.MONATE, coerce=int,
                                    initial=2)  # fmt: skip

    def __init__(self, *args, wahl=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["seite"].choices = list(wahl)
