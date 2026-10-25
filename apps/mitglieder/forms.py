from django import forms
from django.contrib.auth import get_user_model

from apps.adressen.models import Adresse
from apps.core.auswahl import (
    AUSTRITTSGRUENDE,
    MITGLIEDSARTEN,
    ZAHLUNGSARTEN,
    ZAHLWEISEN,
    mit_vorhandenem,
)
from apps.konten.forms import DatumEingabe
from apps.mitglieder.models import Mitglied, MitgliederEinstellungen


def _auswahl(liste, wert, leer=True):
    return mit_vorhandenem(([("", "—")] if leer else []) + [(w, w) for w in liste], wert)


class MitgliedForm(forms.ModelForm):
    adresse = forms.ModelChoiceField(
        label="Adresse (aus dem Adressbuch)", queryset=Adresse.objects.none(),
        help_text="Nicht dabei? Zuerst im Adressbuch anlegen.",
    )  # fmt: skip
    art = forms.ChoiceField(label="Art der Mitgliedschaft")
    zahlweise = forms.ChoiceField(label="Zahlweise", required=False)
    zahlungsart = forms.ChoiceField(label="Zahlungsart", required=False)
    austrittsgrund = forms.ChoiceField(label="Grund des Austritts", required=False)
    benutzer = forms.ModelChoiceField(
        label="Zugleich Mitarbeiter/in (Konto)", required=False,
        queryset=get_user_model().objects.none(),
    )  # fmt: skip

    ABSCHNITTE = [
        ("Mitgliedschaft", ["adresse", "nummer", "art", "eintritt", "benutzer"]),
        ("Beitrag", ["jahresbeitrag", "zahlweise", "zahlungsart"]),
        ("Austritt und Notiz", ["austritt", "austrittsgrund", "notiz"]),
    ]

    class Meta:
        model = Mitglied
        fields = ["adresse", "nummer", "art", "eintritt", "benutzer", "jahresbeitrag",
                  "zahlweise", "zahlungsart", "austritt", "austrittsgrund", "notiz"]  # fmt: skip
        widgets = {"eintritt": DatumEingabe(), "austritt": DatumEingabe(),
                   "notiz": forms.Textarea(attrs={"rows": 3})}  # fmt: skip
        localized_fields = ["jahresbeitrag"]
        help_texts = {"nummer": "Wird beim Anlegen fortlaufend vorgeschlagen."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        m = self.instance
        frei = Adresse.objects.filter(mitglied__isnull=True)
        if m.pk:
            frei = frei | Adresse.objects.filter(pk=m.adresse_id)
        self.fields["adresse"].queryset = frei.order_by("organisation", "nachname")
        self.fields["art"].choices = _auswahl(MITGLIEDSARTEN, m.art, leer=False)
        self.fields["zahlweise"].choices = _auswahl(ZAHLWEISEN, m.zahlweise)
        self.fields["zahlungsart"].choices = _auswahl(ZAHLUNGSARTEN, m.zahlungsart)
        self.fields["austrittsgrund"].choices = _auswahl(AUSTRITTSGRUENDE, m.austrittsgrund)
        konten = get_user_model().objects.filter(mitglied__isnull=True)
        if m.benutzer_id:
            konten = konten | get_user_model().objects.filter(pk=m.benutzer_id)
        self.fields["benutzer"].queryset = konten.order_by("last_name", "first_name", "username")
        self.fields["benutzer"].label_from_instance = lambda b: b.get_full_name() or b.username

    def clean(self):
        daten = super().clean()
        if daten.get("austritt") and not daten.get("austrittsgrund"):
            self.add_error("austrittsgrund", "Bitte den Grund des Austritts wählen.")
        return daten

    def abschnitte(self):
        return [(t, [self[n] for n in namen if n in self.fields]) for t, namen in self.ABSCHNITTE]


class MitgliederEinstellungenForm(forms.ModelForm):
    class Meta:
        model = MitgliederEinstellungen
        fields = ["standard_beitrag", "anteilig", "naechste_nummer"]
        localized_fields = ["standard_beitrag"]
