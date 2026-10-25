from django import forms

from apps.kunden.models import KundenEinstellungen, Zusatzfeld


class KundenEinstellungenForm(forms.ModelForm):
    export_felder = forms.MultipleChoiceField(
        label="Spalten des Exports der Kundenliste", required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leer = Kundennummer, Vorname, Nachname, Kundengruppe, Ausgabetage, Uhrzeit, "
        "Personen. Kontaktdaten, Kontostand und Art.-9-Felder bleiben ohne das passende Recht "
        "leer.",
    )  # fmt: skip

    class Meta:
        model = KundenEinstellungen
        fields = [
            "telefon_erfassen",
            "email_erfassen",
            "staatsangehoerigkeit_erfassen",
            "familienstand_erfassen",
            "bemerkungen_importieren",
            "kind_bis_alter",
            "ausweis_gueltig_monate",
            "ausweis_bis_monatsende",
            "abholungen_aufbewahren_jahre",
            "zugriffe_aufbewahren_tage",
            "historie_aufbewahren_jahre",
            "export_felder",
        ]

    def __init__(self, *args, **kwargs):
        from apps.kunden import export

        super().__init__(*args, **kwargs)
        self.fields["export_felder"].choices = export.auswahl()
        self.initial["export_felder"] = self.instance.export_felder or export.VORGABE

    def clean_export_felder(self):
        from apps.kunden import export

        gewaehlt = set(self.cleaned_data["export_felder"])
        return [k for k, _ in export.auswahl() if k in gewaehlt]


class ZusatzfeldForm(forms.ModelForm):
    class Meta:
        model = Zusatzfeld
        fields = [
            "schluessel",
            "bezeichnung",
            "gilt_fuer",
            "typ",
            "optionen",
            "besondere_kategorie",
            "reihenfolge",
            "aktiv",
        ]
        widgets = {"optionen": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Der Schlüssel verbindet gespeicherte Werte und Importspalte; nicht mehr änderbar.
            self.fields["schluessel"].disabled = True
