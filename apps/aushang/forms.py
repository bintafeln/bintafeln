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


ZEITRAUM = [(f"m{n}", text) for n, text in AushangSeite.MONATE] + [
    ("w", "die nächsten Wochen ab heute")]  # fmt: skip


class ZeitraumForm(forms.Form):
    """Ganze Monate oder die nächsten Wochen ab heute (Anzahl einstellbar)."""

    zeitraum = forms.ChoiceField(label="Zeitraum", choices=ZEITRAUM, initial="m2")
    wochen = forms.IntegerField(label="Anzahl Wochen", min_value=1, max_value=26, initial=9,
                                required=False,
                                help_text="Nur bei „die nächsten Wochen“; so viele, wie gut auf "
                                          "den Monitor passen.")  # fmt: skip

    def werte(self) -> dict:
        """Felder für ``AushangSeite``: monate und wochen."""
        z = self.cleaned_data["zeitraum"]
        if z == "w":
            return {"monate": 2, "wochen": self.cleaned_data["wochen"] or 9}
        return {"monate": int(z[1:]), "wochen": 0}

    @staticmethod
    def fuer(seite: AushangSeite) -> dict:
        return {"zeitraum": "w" if seite.wochen else f"m{seite.monate}",
                "wochen": seite.wochen or 9}  # fmt: skip


class SeiteForm(ZeitraumForm):
    seite = forms.ChoiceField(label="Seite")
    field_order = ["seite", "zeitraum", "wochen"]

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
