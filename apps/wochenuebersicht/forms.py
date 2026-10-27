from django import forms

from apps.ausgabe.ampel import WOCHENTAGE
from apps.wochenuebersicht.models import Selbstabholer, SelbstabholerKontakt, SelbstabholerNotiz


class SelbstabholerForm(forms.ModelForm):
    tage = forms.MultipleChoiceField(
        label="Wochentage", required=False, choices=[(t, t) for t in WOCHENTAGE],
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip

    class Meta:
        model = Selbstabholer
        fields = ["name", "tage", "personen", "aktiv", "strasse", "plz", "ort", "telefon", "email",
                  "notiz"]  # fmt: skip
        widgets = {"notiz": forms.Textarea(attrs={"rows": 3})}

    ABSCHNITTE = [
        ("Einrichtung", ["name", "personen", "tage", "aktiv"]),
        ("Anschrift und Kontakt", ["strasse", "plz", "ort", "telefon", "email"]),
        ("Hinweise", ["notiz"]),
    ]

    def abschnitte(self):
        return [(t, [self[n] for n in namen]) for t, namen in self.ABSCHNITTE]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["tage"] = self.instance.tage_liste

    def clean_tage(self):
        return ", ".join(t for t in WOCHENTAGE if t in self.cleaned_data["tage"])


class KontaktForm(forms.ModelForm):
    class Meta:
        model = SelbstabholerKontakt
        fields = ["name", "funktion", "telefon", "email"]


# Leere Zeilen bleiben ungespeichert; zwei freie Zeilen für neue Ansprechpersonen
KontakteFormset = forms.inlineformset_factory(
    Selbstabholer, SelbstabholerKontakt, form=KontaktForm, extra=2, can_delete=True
)


class NotizForm(forms.ModelForm):
    class Meta:
        model = SelbstabholerNotiz
        fields = ["text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}
        labels = {"text": "Neue Notiz"}
        help_texts = {"text": "Was wurde besprochen? Datum und Ihr Name werden gespeichert."}
