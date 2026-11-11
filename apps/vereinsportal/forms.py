from django import forms

from apps.vereinsportal.models import PortalEinstellungen


class FinanzexportForm(forms.Form):
    finanzexport = forms.FileField(
        label="Finanzexport (ZIP, oder nur dessen Excel-Datei)",
        widget=forms.ClearableFileInput(attrs={"accept": ".zip,.xlsx"}),
    )


class SpenderlisteForm(forms.Form):
    spenderliste = forms.FileField(
        label="Liste „Spender mit E-Mail“ (Excel)",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )


class EinstellungenForm(forms.ModelForm):
    class Meta:
        model = PortalEinstellungen
        fields = ["absender", "aufbewahrung_jahre"]


class BriefForm(forms.Form):
    """Auswahl für die Dankesbriefe."""

    vorlage = forms.ModelChoiceField(
        label="Vorlage", queryset=None,
        help_text="Serienbrief-Vorlage, z. B. mit {anrede}, {name}, {spendensumme}, "
        "{anzahl_spenden}.",
    )  # fmt: skip
    jahr = forms.TypedChoiceField(label="Jahr", coerce=int)
    gruppe = forms.ChoiceField(label="Spender", widget=forms.RadioSelect)

    def __init__(self, *args, jahre=(), **kwargs):
        from apps.serienbriefe.models import Vorlage
        from apps.vereinsportal.auswertung import GRUPPEN

        super().__init__(*args, **kwargs)
        self.fields["vorlage"].queryset = Vorlage.objects.all()
        self.fields["jahr"].choices = [(j, j) for j in jahre]
        self.fields["gruppe"].choices = GRUPPEN
        self.fields["gruppe"].initial = "mehrfach_post"
