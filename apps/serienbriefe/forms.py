from django import forms
from django.utils import timezone

from apps.adressen.models import AdressKategorie
from apps.core.auswahl import MITGLIEDSARTEN
from apps.konten import rollen
from apps.serienbriefe.empfaenger import QUELLEN
from apps.serienbriefe.models import Versand, Vorlage


class VorlageForm(forms.ModelForm):
    class Meta:
        model = Vorlage
        fields = ["name", "betreff", "text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 16})}


class AuswahlForm(forms.Form):
    vorlage = forms.ModelChoiceField(label="Vorlage", queryset=Vorlage.objects.all())
    quelle = forms.ChoiceField(label="Empfänger", widget=forms.RadioSelect)
    versandart = forms.ChoiceField(label="Versand", choices=Versand.Art.choices,
                                   widget=forms.RadioSelect, initial=Versand.Art.BRIEF)  # fmt: skip
    jahr = forms.TypedChoiceField(
        label="Jahr", coerce=int,
        help_text="Für Spender, offene Beiträge und die Platzhalter {spendensumme}, {jahr}.",
    )  # fmt: skip
    kategorien = forms.ModelMultipleChoiceField(
        label="Kategorien (Adressen)", required=False, widget=forms.CheckboxSelectMultiple,
        queryset=AdressKategorie.objects.filter(aktiv=True),
    )  # fmt: skip
    nur_einwilligung = forms.BooleanField(
        label="Adressen und Spender nur mit Einwilligung (Post bzw. E-Mail)", required=False,
        initial=True,
    )  # fmt: skip
    mindestbetrag = forms.DecimalField(label="Spender: Mindestsumme im Jahr (Euro)",
                                       required=False, localize=True)  # fmt: skip
    mitgliedsarten = forms.MultipleChoiceField(
        label="Mitglieder: nur diese Arten", required=False, widget=forms.CheckboxSelectMultiple,
        choices=[(a, a) for a in MITGLIEDSARTEN],
    )  # fmt: skip
    nur_offen = forms.BooleanField(label="Mitglieder: nur mit offenem Beitrag im Jahr",
                                   required=False)  # fmt: skip
    kundengruppen = forms.ModelMultipleChoiceField(
        label="Kunden: nur diese Kundengruppen", required=False,
        widget=forms.CheckboxSelectMultiple, queryset=None,
    )  # fmt: skip

    def __init__(self, *args, benutzer=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.kunden.models import Kundengruppe

        quellen = [q for q in QUELLEN if q[0] != "kunden"
                   or rollen.hat_recht(benutzer, "serienbriefe.kunden")]  # fmt: skip
        self.fields["quelle"].choices = quellen
        self.fields["quelle"].initial = quellen[0][0]
        heute = timezone.localdate().year
        self.fields["jahr"].choices = [(j, j) for j in range(heute, heute - 6, -1)]
        if "kunden" in dict(quellen):
            self.fields["kundengruppen"].queryset = Kundengruppe.objects.all()
        else:
            del self.fields["kundengruppen"]
        from apps.mitglieder.models import MitgliederEinstellungen

        if not MitgliederEinstellungen.mit_beitraegen():
            del self.fields["nur_offen"]
            self.fields[
                "jahr"
            ].help_text = "Für Spender und die Platzhalter {spendensumme}, {jahr}."
