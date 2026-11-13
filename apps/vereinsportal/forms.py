from django import forms
from django.db import models

from apps.core import geheimnis
from apps.konten.forms import DatumEingabe
from apps.vereinsportal.models import PortalEinstellungen, Zugang


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
    class Meta:
        model = PortalEinstellungen
        fields = ["absender", "anmeldung_url", "liste_url", "export_url"]
        formfield_callback = _feld

    def clean(self):
        daten = super().clean()
        for feld in ("anmeldung_url", "liste_url", "export_url"):
            if daten.get(feld) and not daten[feld].startswith("https://"):
                self.add_error(feld, "Die Adresse muss mit https:// beginnen.")
        return daten


class ZugangForm(forms.ModelForm):
    """Die persönlichen Zugangsdaten des angemeldeten Kontos (ADR 0129)."""

    passwort = forms.CharField(
        label="Passwort für die Anmeldung in WISO MeinVerein", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Es wird verschlüsselt gespeichert und nie wieder angezeigt. Leer lassen, um "
        "das gespeicherte Passwort zu behalten.",
    )  # fmt: skip

    class Meta:
        model = Zugang
        fields = ["email"]

    def clean(self):
        daten = super().clean()
        if not daten.get("passwort") and not self.instance.passwort_verschluesselt:
            self.add_error("passwort", "Bitte das Passwort eintragen.")
        return daten

    def save(self, commit=True):
        instanz = super().save(commit=False)
        if self.cleaned_data.get("passwort"):
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
