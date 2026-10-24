from django import forms

from apps.ausgabe.models import AusgabeEinstellungen, BeitragsfreierZeitraum
from apps.konten.forms import DatumEingabe


class AusgabeEinstellungenForm(forms.ModelForm):
    class Meta:
        model = AusgabeEinstellungen
        fields = [
            "max_je_tag",
            "max_abholungen",
            "zeitraum",
            "nicht_dran_rot",
            "vorwarnung_tage",
            "zahlt_ab_alter",
            "beitrag_je_person",
            "zusatzbeitraege",
            "beitrag_je_abholung",
            "beitrag_je_erwachsenem",
            "beitrag_je_kind",
            "kontostand_anzeigen",
            "anschreiben_erlaubt",
            "buchungen_aufbewahren_jahre",
        ]
        # Beträge mit Komma eingeben und anzeigen („1,50“).
        localized_fields = [
            "beitrag_je_person", "beitrag_je_abholung", "beitrag_je_erwachsenem", "beitrag_je_kind",
        ]  # fmt: skip


class BeitragsfreiForm(forms.ModelForm):
    class Meta:
        model = BeitragsfreierZeitraum
        fields = ["bezeichnung", "von", "bis"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}
