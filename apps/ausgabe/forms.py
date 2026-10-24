from django import forms

from apps.ausgabe.models import (
    AusgabeEinstellungen,
    BeitragsfreierZeitraum,
    Sonderaktion,
    SonderaktionAuswahl,
)
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
            "anschreiben_erlaubt",
            "kontostand_anzeigen",
            "einlass_haushaltsgroesse",
            "einlass_geburtsdaten",
            "einlass_abholer",
            "einlass_anschrift",
            "einlass_sperren",
            "einlass_abholungen",
            "einlass_gruppenfarbe",
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


class SonderaktionForm(forms.ModelForm):
    auswahl_text = forms.CharField(
        label="Auswahlmöglichkeiten (eine je Zeile, optional)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Z. B. „Spielzeug“ und „Kleidung“: Am Einlass wird dann eine davon gewählt. "
        "Leer lassen, wenn es nichts zu wählen gibt.",
    )

    class Meta:
        model = Sonderaktion
        fields = ["bezeichnung", "von", "bis", "menge", "nur_mit_kindern", "beschreibung"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["auswahl_text"] = "\n".join(
                a.bezeichnung for a in self.instance.auswahl.all()
            )

    def clean_auswahl_text(self):
        zeilen = []
        for zeile in self.cleaned_data["auswahl_text"].splitlines():
            zeile = zeile.strip()[:100]
            if zeile and zeile.lower() not in (z.lower() for z in zeilen):
                zeilen.append(zeile)
        return zeilen

    def save(self, commit=True):
        aktion = super().save(commit=commit)
        vorhanden = {a.bezeichnung.lower(): a for a in aktion.auswahl.all()}
        for i, name in enumerate(self.cleaned_data["auswahl_text"]):
            eintrag = vorhanden.pop(name.lower(), None) or SonderaktionAuswahl(aktion=aktion)
            eintrag.bezeichnung, eintrag.reihenfolge = name, i
            eintrag.save()
        for weg in vorhanden.values():  # Teilnahmen behalten ihre Menge, nur ohne Auswahl
            weg.delete()
        return aktion
