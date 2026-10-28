from django import forms

from apps.aushang.models import Aushang, AushangSeite


class AushangForm(forms.ModelForm):
    class Meta:
        model = Aushang
        fields = ["name", "aktiv", "nebeneinander", "sekunden", "qr_code", "aendern"]


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


PIN_FELD = {"inputmode": "numeric", "autocomplete": "new-password"}


class PinForm(forms.Form):
    pin = forms.CharField(label="Neue PIN", min_length=6, max_length=12,
                          widget=forms.PasswordInput(attrs=PIN_FELD),
                          help_text="Mindestens 6 Ziffern, nur Sie kennen sie.")  # fmt: skip
    wiederholen = forms.CharField(label="PIN wiederholen", max_length=12,
                                  widget=forms.PasswordInput(attrs=PIN_FELD))  # fmt: skip

    def clean_pin(self):
        wert = self.cleaned_data["pin"]
        if not wert.isdigit():
            raise forms.ValidationError("Bitte nur Ziffern.")
        if len(set(wert)) == 1 or wert in "0123456789" or wert in "9876543210":
            raise forms.ValidationError("Bitte keine einfache Folge wie 111111 oder 123456.")
        return wert

    def clean(self):
        daten = super().clean()
        if daten.get("pin") and daten.get("pin") != daten.get("wiederholen"):
            self.add_error("wiederholen", "Die beiden PINs sind nicht gleich.")
        return daten
