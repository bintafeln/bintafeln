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
        ("Spende", ["art", "adresse", "datum", "betrag", "zweck", "belegnummer"]),
        ("Geldspende", ["zahlungsweg", "mitgliedsbeitrag", "verzicht_aufwand"]),
        ("Sachspende", ["beschreibung", "menge", "einheit", "herkunft", "unterlagen"]),
    ]

    class Meta:
        model = Spende
        fields = ["art", "adresse", "datum", "betrag", "zweck", "belegnummer", "zahlungsweg",
                  "mitgliedsbeitrag",
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
        from apps.mitglieder.models import MitgliederEinstellungen

        if not s.mitgliedsbeitrag and not MitgliederEinstellungen.mit_beitraegen():
            del self.fields["mitgliedsbeitrag"]
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


class DankForm(forms.Form):
    """Auswahl für Dankesbriefe (ADR 0056)."""

    vorlage = forms.ModelChoiceField(
        label="Vorlage", queryset=None,
        help_text="Serienbrief-Vorlage, z. B. mit {anrede}, {spendensumme}, {anzahl_spenden}.",
    )  # fmt: skip
    jahr = forms.TypedChoiceField(label="Jahr", coerce=int)
    art = forms.ChoiceField(label="Spender", initial="alle", widget=forms.RadioSelect)
    nur_offen = forms.BooleanField(label="Nur Spenden ohne Dankesbrief", required=False,
                                   initial=True)  # fmt: skip
    mit_bestaetigungen = forms.BooleanField(
        label="Zuwendungsbestätigungen aus bintafeln beilegen", required=False, initial=True,
        help_text="Fehlende Bestätigungen für Geldspenden werden dabei ausgestellt.",
    )  # fmt: skip
    mit_belegen = forms.BooleanField(
        label="Hochgeladene Belege beilegen (z. B. aus dem Vereinsportal)", required=False,
        initial=True,
    )  # fmt: skip
    mail = forms.BooleanField(
        label="Spender mit E-Mail-Einwilligung per E-Mail anschreiben (Anlagen als PDF)",
        required=False, help_text="Die übrigen bekommen einen Brief.",
    )  # fmt: skip

    def __init__(self, *args, jahre=(), **kwargs):
        from apps.serienbriefe.models import Vorlage
        from apps.spenden.dank import ARTEN

        super().__init__(*args, **kwargs)
        self.fields["vorlage"].queryset = Vorlage.objects.all()
        self.fields["jahr"].choices = [(j, j) for j in jahre]
        self.fields["art"].choices = ARTEN
