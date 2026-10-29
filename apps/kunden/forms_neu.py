"""Neuer Haushalt in der Reihenfolge des Büros (ADR 0025, Ergänzung).

Hauptperson (deren Name auf den Ausweis kommt), Anschrift und Kontakt, weitere Angaben der Tafel
(Zusatzfelder), Angehörige, Bescheid und Gültigkeit, zuletzt die Kundengruppe. Die Kundennummer
wird vergeben; ändern darf sie nur, wer das Recht ``kunden.nummer_aendern`` hat.
"""

import datetime as dt

from django import forms
from django.utils import timezone

from apps.antraege import aufnahme
from apps.core.auswahl import mit_vorhandenem, staatsangehoerigkeiten
from apps.core.forms import StaatAuswahl
from apps.konten.forms import DatumEingabe
from apps.kunden.forms_bearbeiten import BehinderungMixin, HaushaltForm, PersonForm
from apps.kunden.models import Einkommensart, Haushalt, KundenEinstellungen, Kundengruppe, Person


class HauptpersonForm(PersonForm):
    class Meta(PersonForm.Meta):
        fields = [f for f in PersonForm.Meta.fields if f != "ist_hauptperson"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nachname"].required = True


class HaushaltNeuForm(HaushaltForm):
    """Anschrift, Kontakt, Zusatzfelder des Haushalts, Bescheid, Gültigkeit und Gruppe."""

    gueltig_bis = forms.ChoiceField(label="Ausweis gültig bis", required=False)
    gueltig_eigenes = forms.DateField(
        label="Eigenes Datum", required=False, widget=DatumEingabe(),
        help_text="Nur bei „eigenes Datum …“.",
    )  # fmt: skip

    class Meta(HaushaltForm.Meta):
        fields = ["kundennummer", "strasse", "plz", "ort", "telefon", "email", "einkommensart",
                  "kundengruppe"]  # fmt: skip

    def __init__(self, *args, nummer_aendern=False, **kwargs):
        super().__init__(*args, **kwargs)
        heute = timezone.localdate()
        e = KundenEinstellungen.laden()
        self.vorschlag = aufnahme.naechste_kundennummer()
        if nummer_aendern:
            self.initial["kundennummer"] = self.vorschlag
            self.fields[
                "kundennummer"
            ].help_text = "Vorgeschlagen ist die nächste freie Nummer. Nur ändern, wenn nötig."
        else:
            del self.fields["kundennummer"]
        self.fields["einkommensart"].label = "Bescheid / Einkommensart"
        self.fields["einkommensart"].queryset = Einkommensart.objects.filter(aktiv=True)
        self.fields["einkommensart"].empty_label = "– kein Bescheid –"
        self.fields["gueltig_bis"].choices = [
            *aufnahme.gueltigkeit_auswahl(heute, e), ("eigenes", "eigenes Datum …"),
            ("", "noch offen"),
        ]  # fmt: skip
        self.initial.setdefault("gueltig_bis", self.fields["gueltig_bis"].choices[0][0])
        self.gruppen = aufnahme.freie_gruppen()
        self.fields["kundengruppe"].queryset = Kundengruppe.objects.filter(
            pk__in=[g["gruppe"].pk for g in self.gruppen]
        )
        self.fields["kundengruppe"].required = False

    def clean(self):
        daten = super().clean()
        wahl = daten.get("gueltig_bis")
        if wahl == "eigenes":
            datum = daten.get("gueltig_eigenes")
            if not datum:
                self.add_error("gueltig_eigenes", "Bitte das Datum angeben.")
            elif datum < timezone.localdate():
                self.add_error("gueltig_eigenes", "Das Datum liegt in der Vergangenheit.")
            else:
                daten["ausweis_bis"] = datum
        elif wahl:
            daten["ausweis_bis"] = dt.date.fromisoformat(wahl)
        return daten

    def save(self, commit=True):
        h = self.instance
        if "kundennummer" not in self.fields:
            h.kundennummer = aufnahme.naechste_kundennummer()
        h.status = Haushalt.Status.AKTIV
        h.kunde_seit = timezone.localdate()
        h.ausweis_gueltig_bis = self.cleaned_data.get("ausweis_bis")
        return super().save(commit)


class AngehoerigerForm(BehinderungMixin, forms.ModelForm):
    staatsangehoerigkeit = forms.ChoiceField(
        label="Staatsangehörigkeit", required=False, widget=StaatAuswahl
    )

    class Meta:
        model = Person
        fields = ["vorname", "nachname", "geburtsdatum", "staatsangehoerigkeit"]
        widgets = {"geburtsdatum": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vorname"].required = False  # leere Zeilen werden übergangen
        self.fields["nachname"].required = False  # leer: wie die Hauptperson
        if KundenEinstellungen.laden().staatsangehoerigkeit_erfassen:
            self.fields["staatsangehoerigkeit"].choices = mit_vorhandenem(
                staatsangehoerigkeiten(), self.instance.staatsangehoerigkeit
            )
        else:
            del self.fields["staatsangehoerigkeit"]
        self.behinderung_einbauen()

    def save(self, commit=True):
        self.behinderung_uebernehmen()
        return super().save(commit)

    def clean(self):
        daten = super().clean()
        if (daten.get("nachname") or daten.get("geburtsdatum")) and not daten.get("vorname"):
            self.add_error("vorname", "Bitte den Vornamen angeben.")
        return daten


AngehoerigeFormset = forms.modelformset_factory(Person, form=AngehoerigerForm, extra=6)
