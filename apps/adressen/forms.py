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
        ("Mitarbeit", ["helfer", "helfer_aktiv", "fahrdienst", "konto"]),
        ("Einwilligungen und Notiz", ["einwilligung_post", "einwilligung_email",
                                      "veroeffentlichen", "notiz"]),
    ]  # fmt: skip

    class Meta:
        model = Adresse
        fields = [
            "art", "organisation", "ansprechperson", "anrede", "vorname", "nachname", "kategorien",
            "strasse", "plz", "ort", "land", "telefon", "mobil", "email", "webseite",
            "helfer", "helfer_aktiv", "fahrdienst",
            "einwilligung_post", "einwilligung_email", "veroeffentlichen", "notiz",
        ]  # fmt: skip
        widgets = {
            "einwilligung_post": DatumEingabe(),
            "einwilligung_email": DatumEingabe(),
            "veroeffentlichen": DatumEingabe(),
            "notiz": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, konto_waehlbar=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, self.instance.anrede)
        # Helfer-Felder nur bei einer Person zeigen (Umschalten über data-zeigen-bei)
        for name in ("helfer", "helfer_aktiv", "fahrdienst"):
            self.fields[name].widget.attrs["data-zeigen-bei"] = "art=person"
        # Das Konto darf nur verknüpfen, wer Mitarbeitende verwalten darf.
        if konto_waehlbar:
            from apps.konten.models import Benutzer

            frei = Benutzer.objects.filter(stelle__isnull=True).filter(
                Q(adresse__isnull=True) | Q(adresse=self.instance if self.instance.pk else None)
            )
            self.fields["konto"] = forms.ModelChoiceField(
                label="Konto",
                required=False,
                queryset=frei.order_by("last_name", "first_name"),
                help_text=Adresse._meta.get_field("konto").help_text,
                widget=forms.Select(attrs={"data-zeigen-bei": "art=person"}),
            )
            self.initial.setdefault("konto", self.instance.konto_id)
        gewaehlt = list(self.instance.kategorien.values_list("pk", flat=True)) if (
            self.instance.pk) else []  # fmt: skip
        self.fields["kategorien"].queryset = AdressKategorie.objects.filter(
            Q(aktiv=True) | Q(pk__in=gewaehlt)  # gespeicherte bleiben wählbar
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("art") == Adresse.Art.ORGANISATION and cleaned.get("konto"):
            self.add_error("konto", "Ein Konto gibt es nur bei einer Person.")
        return cleaned

    def save(self, commit=True):
        # „konto“ ist kein Meta-Feld (nur für Berechtigte da), deshalb von Hand übernehmen.
        if "konto" in self.fields:
            self.instance.konto = self.cleaned_data.get("konto")
        return super().save(commit=commit)

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
