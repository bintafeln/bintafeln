from django import forms

from apps.kunden.models import KundenEinstellungen, Zusatzfeld


class KundenEinstellungenForm(forms.ModelForm):
    class Meta:
        model = KundenEinstellungen
        fields = [
            "telefon_erfassen",
            "email_erfassen",
            "staatsangehoerigkeit_erfassen",
            "familienstand_erfassen",
            "bemerkungen_importieren",
            "kind_bis_alter",
            "besondere_kategorie_fuer_ausgabe",
        ]


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
