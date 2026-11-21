from django import forms

from apps.fahrdienst.forms import TageFeld
from apps.touren.models import Station


class StationForm(forms.ModelForm):
    abholtage = TageFeld(label="Abholtage", required=False,
                         help_text="An diesen Wochentagen wird abgeholt.")  # fmt: skip

    class Meta:
        model = Station
        fields = [
            "name", "art", "kette", "filialnummer", "strasse", "hausnummer", "plz", "ort",
            "ortsteil", "telefon", "email", "email_lieferschein", "ansprechpartner",
            "oeffnungszeiten", "abholtage", "abholzeit", "anfahrt", "lieferschein", "aktiv",
            "kennung", "breite", "laenge", "notiz",
        ]  # fmt: skip
        widgets = {"anfahrt": forms.Textarea(attrs={"rows": 3}),
                   "notiz": forms.Textarea(attrs={"rows": 3})}  # fmt: skip

    def clean(self):
        daten = super().clean()
        if (daten.get("breite") is None) != (daten.get("laenge") is None):
            self.add_error("laenge", "Breiten- und Längengrad nur zusammen angeben.")
        return daten


def neue_kennung() -> str:
    """Kennung für eine von Hand angelegte Station: S-1, S-2 … (die nächste freie)."""
    nummern = [int(k[2:]) for k in Station.objects.filter(kennung__regex=r"^S-\d+$")
               .values_list("kennung", flat=True)]  # fmt: skip
    return f"S-{max(nummern, default=0) + 1}"
