from django import forms
from django.db import models

from apps.core import geheimnis
from apps.konten.forms import DatumEingabe
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


def _feld(feld, **angaben):
    """Adressen ohne „https://“ davor gelten als https (Vorgabe ab Django 6)."""
    if isinstance(feld, models.URLField):
        angaben["assume_scheme"] = "https"
    return feld.formfield(**angaben)


class EinstellungenForm(forms.ModelForm):
    passwort = forms.CharField(
        label="Passwort für die Anmeldung im Vereinsportal", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Leer lassen, um das gespeicherte Passwort zu behalten. Es wird verschlüsselt "
        "gespeichert und nie wieder angezeigt.",
    )  # fmt: skip
    passwort_loeschen = forms.BooleanField(label="Gespeichertes Passwort löschen", required=False)

    class Meta:
        model = PortalEinstellungen
        fields = ["absender", "aufbewahrung_jahre", "anmeldung_url", "liste_url", "export_url",
                  "email"]  # fmt: skip
        formfield_callback = _feld

    def clean(self):
        daten = super().clean()
        for feld in ("anmeldung_url", "liste_url", "export_url"):
            if daten.get(feld) and not daten[feld].startswith("https://"):
                self.add_error(feld, "Die Adresse muss mit https:// beginnen.")
        return daten

    def save(self, commit=True):
        instanz = super().save(commit=False)
        if self.cleaned_data.get("passwort_loeschen"):
            instanz.passwort_verschluesselt = ""
        elif self.cleaned_data.get("passwort"):
            instanz.passwort_verschluesselt = geheimnis.verschluesseln(
                self.cleaned_data["passwort"]
            )
        if commit:
            instanz.save()
        return instanz


class AbrufForm(forms.Form):
    """Zeitraum für den automatischen Abruf (ADR 0127)."""

    von = forms.DateField(label="Spenden von", widget=DatumEingabe())
    bis = forms.DateField(label="bis", widget=DatumEingabe())
    mit_liste = forms.BooleanField(
        label="Auch die Liste „Spender mit E-Mail“ neu holen", required=False, initial=True
    )

    def clean(self):
        from apps.vereinsportal import abruf

        daten = super().clean()
        if daten.get("von") and daten.get("bis"):
            try:
                abruf.zeitraum_pruefen(daten["von"], daten["bis"])
            except abruf.AbrufFehler as fehler:
                raise forms.ValidationError(str(fehler)) from None
        return daten


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
