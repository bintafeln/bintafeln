from django import forms

from apps.konten.forms import DatumEingabe
from apps.personal.models import Abwesenheit, Arbeitsvertrag, Stunden, Urlaubsjahr


class VertragForm(forms.ModelForm):
    class Meta:
        model = Arbeitsvertrag
        fields = [
            "beginn", "ende", "taetigkeit", "wochenstunden", "urlaubstage", "stundenlohn",
            "bemerkung",
        ]  # fmt: skip
        widgets = {
            "beginn": DatumEingabe(),
            "ende": DatumEingabe(),
            "bemerkung": forms.Textarea(attrs={"rows": 2}),
        }
        localized_fields = ["wochenstunden", "urlaubstage", "stundenlohn"]


class AbwesenheitForm(forms.ModelForm):
    class Meta:
        model = Abwesenheit
        fields = ["art", "von", "bis", "tage", "au_vorgelegt", "bemerkung"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}
        localized_fields = ["tage"]


class UrlaubsjahrForm(forms.ModelForm):
    class Meta:
        model = Urlaubsjahr
        fields = ["anspruch", "verfall_am"]
        widgets = {"verfall_am": DatumEingabe()}
        localized_fields = ["anspruch"]


class StundenForm(forms.ModelForm):
    class Meta:
        model = Stunden
        fields = ["datum", "stunden", "bemerkung"]
        widgets = {"datum": DatumEingabe()}
        localized_fields = ["stunden"]
