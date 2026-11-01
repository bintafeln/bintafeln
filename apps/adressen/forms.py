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

    rollen = forms.MultipleChoiceField(
        label="Rollen", required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Die Rollen entscheiden über Rechte und die Einteilung in Dienst-/Fahrdienstplan "
        "(Fahrer/Beifahrer). Jedes Konto braucht mindestens eine Rolle.",
    )  # fmt: skip

    ABSCHNITTE = [
        ("Name", ["art", "organisation", "ansprechperson", "anrede", "vorname", "nachname",
                  "kategorien"]),
        ("Anschrift und Kontakt", ["strasse", "plz", "ort", "land", "telefon", "mobil", "email",
                                   "webseite"]),
        ("Mitarbeit", ["konto", "rollen"]),
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

    def __init__(self, *args, konto_waehlbar=False, verwalter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.verwalter = verwalter
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, self.instance.anrede)
        # Das Konto darf nur verknüpfen, wer Mitarbeitende verwalten darf. Dann auch die Rollen.
        self.rollen_bearbeitbar = konto_waehlbar and verwalter is not None
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
        if self.rollen_bearbeitbar:
            from apps.konten import verwaltung

            self.fields["rollen"].choices = [
                (r, r) for r in verwaltung.vergebbare_rollen(verwalter)
            ]
            self.fields["rollen"].widget.attrs["data-zeigen-bei"] = "art=person"
            konto = self.instance.konto if self.instance.pk else None
            if konto is not None:
                self.initial.setdefault("rollen", list(konto.groups.values_list("name", flat=True)))
        else:
            del self.fields["rollen"]
        gewaehlt = list(self.instance.kategorien.values_list("pk", flat=True)) if (
            self.instance.pk) else []  # fmt: skip
        self.fields["kategorien"].queryset = AdressKategorie.objects.filter(
            Q(aktiv=True) | Q(pk__in=gewaehlt)  # gespeicherte bleiben wählbar
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("art") == Adresse.Art.ORGANISATION and cleaned.get("konto"):
            self.add_error("konto", "Ein Konto gibt es nur bei einer Person.")
        # Jedes aktive Konto braucht mindestens eine Rolle (ADR 0097). Gesperrte (ausgeschiedene)
        # Personen dürfen ohne Rolle geführt werden – so bleiben sie als reine Adresse erhalten.
        if self.rollen_bearbeitbar and cleaned.get("konto") and cleaned["konto"].is_active:
            from apps.konten import verwaltung

            gewaehlt = set(cleaned.get("rollen") or [])
            behalten = set(cleaned["konto"].groups.values_list("name", flat=True)) - set(
                verwaltung.vergebbare_rollen(self.verwalter)
            )
            if not gewaehlt and not behalten:
                self.add_error("rollen", "Jedes aktive Konto braucht mindestens eine Rolle. "
                               "Hört die Person auf? „Konto sperren“ auf ihrer Adressseite – sie "
                               "bleibt dann als Adresse erhalten.")  # fmt: skip
        return cleaned

    def save(self, commit=True):
        # „konto“ ist kein Meta-Feld (nur für Berechtigte da), deshalb von Hand übernehmen.
        if "konto" in self.fields:
            self.instance.konto = self.cleaned_data.get("konto")
        return super().save(commit=commit)

    def rollen_anwenden(self) -> None:
        """Die gewählten Rollen auf das verknüpfte Konto schreiben (nach dem Speichern aufrufen)."""
        if self.rollen_bearbeitbar and self.instance.konto_id:
            from apps.konten import verwaltung

            verwaltung.rollen_setzen(
                self.verwalter, self.instance.konto, self.cleaned_data.get("rollen") or []
            )

    def abschnitte(self):
        alle = (
            (titel, [self[n] for n in namen if n in self.fields])
            for titel, namen in self.ABSCHNITTE
        )
        return [(titel, felder) for titel, felder in alle if felder]


class AdressKategorieForm(forms.ModelForm):
    class Meta:
        model = AdressKategorie
        fields = ["name", "aktiv", "reihenfolge"]


class ImportForm(forms.Form):
    datei = forms.FileField(
        label="CSV-Datei",
        help_text="Trennzeichen Semikolon, erste Zeile mit Spaltennamen (siehe Hilfe).",
    )
