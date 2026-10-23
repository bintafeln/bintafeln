from django import forms

from apps.ausgabe.models import AusgabeEinstellungen


class AusgabeEinstellungenForm(forms.ModelForm):
    class Meta:
        model = AusgabeEinstellungen
        fields = [
            "max_abholungen",
            "zeitraum",
            "nicht_dran_rot",
            "vorwarnung_tage",
            "beitrag_je_abholung",
            "beitrag_je_erwachsenem",
            "beitrag_je_kind",
            "kontostand_anzeigen",
            "anschreiben_erlaubt",
            "buchungen_aufbewahren_jahre",
        ]
        # Beträge mit Komma eingeben und anzeigen („1,50“).
        localized_fields = ["beitrag_je_abholung", "beitrag_je_erwachsenem", "beitrag_je_kind"]
