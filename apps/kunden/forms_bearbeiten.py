"""Formulare zum Bearbeiten des Kundenstamms durch den Admin (ADR 0025).

Feste Werte und registrierte Mitarbeitende sind Auswahlfelder (CLAUDE.md); gespeicherte Werte,
die nicht mehr in der Liste stehen, bleiben wählbar.
"""

import datetime as dt

from django import forms
from django.contrib.auth import get_user_model

from apps.ausgabe.ampel import WOCHENTAGE
from apps.core.auswahl import ANREDEN, FAMILIENSTAENDE, mit_vorhandenem
from apps.konten.forms import DatumEingabe
from apps.kunden.models import (
    Abholer,
    Ausgabestelle,
    Ausnahme,
    Bemerkung,
    Einkommensart,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    Zusatzfeld,
)

JA_NEIN = [("", "—"), ("ja", "ja"), ("nein", "nein")]


def mitarbeitende(wert: str) -> list[tuple[str, str]]:
    namen = [str(b) for b in get_user_model().objects.filter(is_active=True).order_by(
        "last_name", "first_name", "username")]  # fmt: skip
    return mit_vorhandenem([("", "—")] + [(n, n) for n in namen], wert)


class ZusatzMixin:
    """Fügt die aktiven Zusatzfelder (Haushalt oder Person) als Eingabefelder hinzu."""

    zusatz_fuer = ""

    def zusatz_einbauen(self):
        self.zusatzfelder = list(Zusatzfeld.objects.filter(aktiv=True, gilt_fuer=self.zusatz_fuer))
        werte = self.instance.zusatz or {}
        for z in self.zusatzfelder:
            name, wert = f"zusatz_{z.schluessel}", werte.get(z.schluessel)
            label = z.bezeichnung + (" (Art. 9)" if z.besondere_kategorie else "")
            if z.typ == Zusatzfeld.Typ.JA_NEIN:
                feld = forms.ChoiceField(choices=JA_NEIN)
                anfang = "" if wert is None else ("ja" if wert else "nein")
            elif z.typ == Zusatzfeld.Typ.DATUM:
                feld = forms.DateField(widget=DatumEingabe())
                anfang = dt.date.fromisoformat(wert) if wert else None
            elif z.typ == Zusatzfeld.Typ.AUSWAHL:
                auswahl = [("", "—")] + [(o, o) for o in z.optionen_liste()]
                feld = forms.ChoiceField(choices=mit_vorhandenem(auswahl, wert or ""))
                anfang = wert or ""
            else:
                feld = forms.CharField(max_length=500)
                anfang = wert or ""
            feld.label, feld.required = label, False
            self.fields[name] = feld
            self.initial[name] = anfang

    def zusatz_uebernehmen(self):
        """Nur die angezeigten Felder ändern; Werte inaktiver Felder bleiben erhalten."""
        werte = dict(self.instance.zusatz or {})
        for z in self.zusatzfelder:
            wert = self.cleaned_data.get(f"zusatz_{z.schluessel}")
            if wert in (None, ""):
                werte.pop(z.schluessel, None)
            elif z.typ == Zusatzfeld.Typ.JA_NEIN:
                werte[z.schluessel] = wert == "ja"
            elif z.typ == Zusatzfeld.Typ.DATUM:
                werte[z.schluessel] = wert.isoformat()
            else:
                werte[z.schluessel] = wert
        self.instance.zusatz = werte


class HaushaltForm(ZusatzMixin, forms.ModelForm):
    zusatz_fuer = Zusatzfeld.GiltFuer.HAUSHALT

    class Meta:
        model = Haushalt
        fields = [
            "kundennummer", "status", "kundengruppe", "kunde_seit", "ausweis_gueltig_bis",
            "letzter_besuch", "einkommensart", "strasse", "plz", "ort", "telefon", "email",
            "anzahl_erwachsene", "anzahl_kinder",
        ]  # fmt: skip
        widgets = {
            "kunde_seit": DatumEingabe(),
            "ausweis_gueltig_bis": DatumEingabe(),
            "letzter_besuch": DatumEingabe(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        e = KundenEinstellungen.laden()
        if not e.telefon_erfassen:
            del self.fields["telefon"]
        if not e.email_erfassen:
            del self.fields["email"]
        self.fields["kundennummer"].help_text = (
            "Ändern nur, wenn sie auch im Altsystem geändert wurde. Frühere Abholungen und "
            "Buchungen behalten die alte Nummer."
        )
        self.zusatz_einbauen()

    def save(self, commit=True):
        self.zusatz_uebernehmen()
        return super().save(commit)


class PersonForm(ZusatzMixin, forms.ModelForm):
    zusatz_fuer = Zusatzfeld.GiltFuer.PERSON
    anrede = forms.ChoiceField(label="Anrede", required=False)
    familienstand = forms.ChoiceField(label="Familienstand", required=False)

    class Meta:
        model = Person
        fields = [
            "ist_hauptperson", "anrede", "vorname", "nachname", "geburtsdatum",
            "staatsangehoerigkeit", "familienstand",
        ]  # fmt: skip
        widgets = {"geburtsdatum": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p, e = self.instance, KundenEinstellungen.laden()
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, p.anrede)
        self.fields["familienstand"].choices = mit_vorhandenem(
            [("", "—")] + [(f, f) for f in FAMILIENSTAENDE], p.familienstand
        )
        if not e.staatsangehoerigkeit_erfassen:
            del self.fields["staatsangehoerigkeit"]
        if not e.familienstand_erfassen:
            del self.fields["familienstand"]
        self.zusatz_einbauen()

    def save(self, commit=True):
        self.zusatz_uebernehmen()
        return super().save(commit)


class AbholerForm(forms.ModelForm):
    class Meta:
        model = Abholer
        fields = ["vorname", "nachname", "geburtsdatum", "eigene_kundennummer"]
        widgets = {"geburtsdatum": DatumEingabe()}


class MitVonMixin:
    """„Eingetragen von“ als Auswahl registrierter Mitarbeitender, vorbelegt mit sich selbst."""

    von_feld = "eingetragen_von"

    def von_einbauen(self, angemeldet):
        wert = getattr(self.instance, self.von_feld)
        self.fields[self.von_feld] = forms.ChoiceField(
            label=self.instance._meta.get_field(self.von_feld).verbose_name,
            choices=mitarbeitende(wert),
            required=False,
        )
        if not self.instance.pk and angemeldet is not None:
            self.initial[self.von_feld] = str(angemeldet)


class SperreForm(MitVonMixin, forms.ModelForm):
    class Meta:
        model = Sperre
        fields = ["von", "bis", "begruendung", "eingetragen_von"]
        widgets = {
            "von": DatumEingabe(),
            "bis": DatumEingabe(),
            "begruendung": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, angemeldet=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.von_einbauen(angemeldet)

    def clean(self):
        daten = super().clean()
        if daten.get("von") and daten.get("bis") and daten["bis"] < daten["von"]:
            self.add_error("bis", "„Bis“ darf nicht vor „Von“ liegen.")
        return daten


class AnmerkungForm(MitVonMixin, forms.ModelForm):
    von_feld = "verfasst_von"

    class Meta:
        model = Bemerkung
        fields = ["datum", "text", "verfasst_von"]
        widgets = {"datum": DatumEingabe(), "text": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, angemeldet=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.von_einbauen(angemeldet)


class AusnahmeForm(MitVonMixin, forms.ModelForm):
    class Meta:
        model = Ausnahme
        fields = ["datum", "begruendung", "eingetragen_von"]
        widgets = {"datum": DatumEingabe(), "begruendung": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, angemeldet=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.von_einbauen(angemeldet)


# --- Listen: Kundengruppen, Ausgabestellen, Einkommensarten -------------------------------


class KundengruppeForm(forms.ModelForm):
    wochentage = forms.MultipleChoiceField(
        label="Wochentage",
        required=False,
        choices=[(t, t) for t in WOCHENTAGE],
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Kundengruppe
        fields = ["kuerzel", "name", "ausgabestelle", "wochentage", "uhrzeit", "maximum", "aktiv"]
        widgets = {"uhrzeit": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["wochentage"] = [
            t.strip() for t in (self.instance.wochentage or "").split(",") if t.strip()
        ]

    def clean_wochentage(self):
        return ", ".join(t for t in WOCHENTAGE if t in self.cleaned_data["wochentage"])


class AusgabestelleForm(forms.ModelForm):
    class Meta:
        model = Ausgabestelle
        fields = ["name", "aktiv"]


class EinkommensartForm(forms.ModelForm):
    class Meta:
        model = Einkommensart
        fields = ["bezeichnung", "aktiv"]
