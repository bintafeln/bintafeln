from django import forms

from apps.ausgabe.ampel import MELDUNGEN
from apps.ausgabe.models import (
    AusgabeEinstellungen,
    BeitragsfreierZeitraum,
    Sonderaktion,
    SonderaktionAuswahl,
    Sonderausgabe,
)
from apps.konten.forms import DatumEingabe
from apps.kunden.models import Ausgabestelle, Kundengruppe


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        texte = self.instance.meldungstexte or {}
        for art, bezeichnung, standard, platzhalter in MELDUNGEN:
            hilfe = f"Standard: „{standard}“."
            if platzhalter:
                hilfe += " Platzhalter: " + ", ".join("{" + p + "}" for p in platzhalter) + "."
            self.fields[f"text_{art}"] = forms.CharField(
                label=f"Text der Ampel: {bezeichnung}", required=False, max_length=200,
                help_text=hilfe, initial=texte.get(art, ""),
                widget=forms.TextInput(attrs={"placeholder": "leer = Standard"}),
            )  # fmt: skip

    ABSCHNITTE = [
        ("Ampel", ["max_je_tag", "max_abholungen", "zeitraum", "nicht_dran_rot",
                   "vorwarnung_tage"]),
        ("Beitrag", ["zahlt_ab_alter", "beitrag_je_person", "anschreiben_erlaubt",
                     "kontostand_anzeigen", "zusatzbeitraege", "beitrag_je_abholung",
                     "beitrag_je_erwachsenem", "beitrag_je_kind"]),
        ("Was der Einlass zeigt", ["einlass_haushaltsgroesse", "einlass_geburtsdaten",
                                   "einlass_abholer", "einlass_anschrift", "einlass_sperren",
                                   "einlass_abholungen", "einlass_gruppenfarbe"]),
        ("Aufbewahrung", ["buchungen_aufbewahren_jahre"]),
    ]  # fmt: skip

    def abschnitte(self):
        return [(t, [self[n] for n in namen if n in self.fields]) for t, namen in self.ABSCHNITTE]

    def texte(self):
        return [self[f"text_{art}"] for art, *_ in MELDUNGEN]

    def save(self, commit=True):
        self.instance.meldungstexte = {
            art: self.cleaned_data[f"text_{art}"].strip()
            for art, *_ in MELDUNGEN
            if self.cleaned_data.get(f"text_{art}", "").strip()
        }
        return super().save(commit)


class BeitragsfreiForm(forms.ModelForm):
    class Meta:
        model = BeitragsfreierZeitraum
        fields = ["bezeichnung", "von", "bis"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}


class GruppenAuswahl(forms.ModelMultipleChoiceField):
    def label_from_instance(self, g):
        teile = [t for t in (g.ausgabestelle.name if g.ausgabestelle else "", g.wochentage) if t]
        return f"{g.name} ({', '.join(teile)})" if teile else g.name


class SonderausgabeForm(forms.ModelForm):
    """Außerplanmäßige Ausgabe (ADR 0072): Wochentag und/oder einzelne Kundengruppen."""

    kundengruppen = GruppenAuswahl(
        queryset=Kundengruppe.objects.none(), required=False, label="Einzelne Kundengruppen",
        widget=forms.CheckboxSelectMultiple,
        help_text="Zusätzlich oder statt des Wochentags; auch mehrere.",
    )  # fmt: skip

    class Meta:
        model = Sonderausgabe
        fields = ["datum", "ausgabestelle", "wie_wochentag", "kundengruppen", "anmerkung"]
        widgets = {"datum": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ausgabestelle"].queryset = Ausgabestelle.objects.order_by("name")
        gruppen = Kundengruppe.objects.filter(aktiv=True)
        if self.instance.pk:  # schon gewählte, inzwischen inaktive Gruppen bleiben wählbar
            gruppen = gruppen | self.instance.kundengruppen.all()
        gruppen = gruppen.distinct().select_related("ausgabestelle")
        self.fields["kundengruppen"].queryset = gruppen.order_by("ausgabestelle__name", "name")
        self.fields["wie_wochentag"].choices = [("", "– keiner –"), *Sonderausgabe.TAGE]

    def clean(self):
        daten = super().clean()
        if not daten.get("wie_wochentag") and not daten.get("kundengruppen"):
            raise forms.ValidationError(
                "Bitte einen Wochentag oder mindestens eine Kundengruppe wählen – sonst ist an "
                "diesem Tag niemand dran."
            )
        return daten


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
