from django import forms
from django.db.models import Q

from apps.adressen.models import Adresse, AdressKategorie
from apps.core.auswahl import ANREDEN, mit_vorhandenem
from apps.konten.forms import DatumEingabe


class AdresseForm(forms.ModelForm):
    anrede = forms.ChoiceField(label="Anrede", required=False)
    webseite = forms.URLField(label="Webseite", required=False, assume_scheme="https")
    kategorien = forms.ModelMultipleChoiceField(
        label="Kategorien", queryset=AdressKategorie.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip

    ABSCHNITTE = [
        ("Name", ["art", "organisation", "ansprechperson", "anrede", "vorname", "nachname",
                  "kategorien"]),
        ("Anschrift und Kontakt", ["strasse", "plz", "ort", "land", "telefon", "mobil", "email",
                                   "webseite"]),
        ("Einwilligungen und Notiz", ["einwilligung_post", "einwilligung_email",
                                      "veroeffentlichen", "notiz"]),
    ]  # fmt: skip

    class Meta:
        model = Adresse
        fields = [
            "art", "organisation", "ansprechperson", "anrede", "vorname", "nachname", "kategorien",
            "strasse", "plz", "ort", "land", "telefon", "mobil", "email", "webseite",
            "einwilligung_post", "einwilligung_email", "veroeffentlichen", "notiz",
        ]  # fmt: skip
        widgets = {
            "einwilligung_post": DatumEingabe(),
            "einwilligung_email": DatumEingabe(),
            "veroeffentlichen": DatumEingabe(),
            "notiz": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, self.instance.anrede)
        gewaehlt = list(self.instance.kategorien.values_list("pk", flat=True)) if (
            self.instance.pk) else []  # fmt: skip
        self.fields["kategorien"].queryset = AdressKategorie.objects.filter(
            Q(aktiv=True) | Q(pk__in=gewaehlt)  # gespeicherte bleiben wählbar
        )

    def abschnitte(self):
        return [
            (titel, [self[n] for n in namen if n in self.fields])
            for titel, namen in self.ABSCHNITTE
        ]


class AdressKategorieForm(forms.ModelForm):
    class Meta:
        model = AdressKategorie
        fields = ["name", "aktiv", "reihenfolge"]


class ImportForm(forms.Form):
    datei = forms.FileField(
        label="CSV-Datei",
        help_text="Trennzeichen Semikolon, erste Zeile mit Spaltennamen (siehe Hilfe).",
    )
