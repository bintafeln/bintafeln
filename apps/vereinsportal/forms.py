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
