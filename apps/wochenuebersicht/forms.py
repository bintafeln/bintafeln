from django import forms

from apps.ausgabe.ampel import WOCHENTAGE
from apps.wochenuebersicht.models import Selbstabholer


class SelbstabholerForm(forms.ModelForm):
    tage = forms.MultipleChoiceField(
        label="Wochentage", required=False, choices=[(t, t) for t in WOCHENTAGE],
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip

    class Meta:
        model = Selbstabholer
        fields = ["name", "tage", "personen", "aktiv", "notiz"]
        widgets = {"notiz": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["tage"] = self.instance.tage_liste

    def clean_tage(self):
        return ", ".join(t for t in WOCHENTAGE if t in self.cleaned_data["tage"])
