from django import forms
from django.utils import timezone

from apps.adressen.models import Adresse
from apps.core.auswahl import SACH_EINHEITEN, ZAHLUNGSWEGE, mit_vorhandenem
from apps.konten.forms import DatumEingabe
from apps.spenden.models import Spende, SpendenEinstellungen


class SpendeForm(forms.ModelForm):
    adresse = forms.ModelChoiceField(
        label="Spender (aus dem Adressbuch)", queryset=Adresse.objects.none(),
        help_text="Nicht dabei? Zuerst im Adressbuch anlegen.",
    )  # fmt: skip
    zahlungsweg = forms.ChoiceField(label="Zahlungsweg", required=False)
    einheit = forms.ChoiceField(label="Einheit", required=False)

    ABSCHNITTE = [
        ("Spende", ["art", "adresse", "datum", "betrag", "zweck"]),
        ("Geldspende", ["zahlungsweg", "mitgliedsbeitrag", "verzicht_aufwand"]),
        ("Sachspende", ["beschreibung", "menge", "einheit", "herkunft", "unterlagen"]),
    ]

    class Meta:
        model = Spende
        fields = ["art", "adresse", "datum", "betrag", "zweck", "zahlungsweg", "mitgliedsbeitrag",
                  "verzicht_aufwand", "beschreibung", "menge", "einheit", "herkunft",
                  "unterlagen"]  # fmt: skip
        widgets = {"datum": DatumEingabe(), "art": forms.RadioSelect}
        localized_fields = ["betrag", "menge"]  # „50,00“ wie gewohnt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = self.instance
        self.fields["adresse"].queryset = Adresse.objects.order_by("organisation", "nachname")
        self.fields["zahlungsweg"].choices = mit_vorhandenem(
            [("", "—")] + [(w, w) for w in ZAHLUNGSWEGE], s.zahlungsweg
        )
        self.fields["einheit"].choices = mit_vorhandenem(
            [("", "—")] + [(w, w) for w in SACH_EINHEITEN], s.einheit
        )
        if not s.pk and not self.initial.get("datum"):
            self.initial["datum"] = timezone.localdate()

    def abschnitte(self):
        return [(t, [self[n] for n in namen if n in self.fields]) for t, namen in self.ABSCHNITTE]


class SpendenEinstellungenForm(forms.ModelForm):
    class Meta:
        model = SpendenEinstellungen
        fields = ["koerperschaft", "anschrift", "zwecke", "grundlage", "finanzamt", "steuernummer",
                  "bescheid_vom", "veranlagungszeitraum", "mitgliedsbeitraege_abziehbar",
                  "unterzeichnet_von", "ort", "naechste_nummer"]  # fmt: skip
        widgets = {"bescheid_vom": DatumEingabe(), "zwecke": forms.Textarea(attrs={"rows": 3})}
