from django import forms

from apps.ausgabe.ampel import WOCHENTAGE
from apps.wochenuebersicht.auswertung import TAGNAMEN
from apps.wochenuebersicht.models import (
    EigeneListe,
    Selbstabholer,
    SelbstabholerKontakt,
    SelbstabholerNotiz,
)


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


class EigeneListeForm(forms.ModelForm):
    """Name, kurze Adresse und die Tage in der gewünschten Reihenfolge (je Platz ein Auswahlmenü).
    Nicht genannte Tage folgen danach in der gewohnten Reihenfolge."""

    PLAETZE = [f"platz_{i}" for i in range(1, 8)]

    class Meta:
        model = EigeneListe
        fields = ["name", "kurz"]
        widgets = {"kurz": forms.TextInput(attrs={"data-autosave-spaet": ""})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bisher = self.instance.tage_liste
        wahl = [("", "–"), *zip(WOCHENTAGE, TAGNAMEN, strict=True)]
        for i, feld in enumerate(self.PLAETZE):
            self.fields[feld] = forms.ChoiceField(
                label=f"{i + 1}. Tag", choices=wahl, required=False,
                initial=bisher[i] if i < len(bisher) else "",
            )  # fmt: skip

    def abschnitte(self):
        return [("Liste", [self["name"], self["kurz"]]),
                ("Reihenfolge der Tage", [self[f] for f in self.PLAETZE])]  # fmt: skip

    def clean(self):
        daten = super().clean()
        tage = [daten[f] for f in self.PLAETZE if daten.get(f)]
        if len(tage) != len(set(tage)):
            raise forms.ValidationError("Jeder Tag darf in der Reihenfolge nur einmal stehen.")
        self.instance.tage = ",".join(tage)
        return daten
