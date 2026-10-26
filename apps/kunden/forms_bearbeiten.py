"""Formulare zum Bearbeiten des Kundenstamms durch den Admin (ADR 0025).

Feste Werte und registrierte Mitarbeitende sind Auswahlfelder (CLAUDE.md); gespeicherte Werte,
die nicht mehr in der Liste stehen, bleiben wählbar.
"""

import datetime as dt
import json

from django import forms
from django.contrib.auth import get_user_model

from apps.ausgabe.ampel import WOCHENTAGE
from apps.core.auswahl import (
    ANREDEN,
    FAMILIENSTAENDE,
    FESTE_ANLIEGEN,
    NACHRICHT_ANLIEGEN_ALT,
    ZEITARTEN,
    ZUSTAENDIGKEITEN,
    mit_vorhandenem,
    staatsangehoerigkeiten,
)
from apps.core.forms import StaatAuswahl
from apps.konten.forms import DatumEingabe
from apps.kunden.models import (
    Abholer,
    Ausgabestelle,
    AusgabestelleKontakt,
    AusgabestelleZeit,
    Ausnahme,
    AusweisVorlage,
    Bemerkung,
    Dokumentart,
    Einkommensart,
    Haushalt,
    HaushaltDokument,
    KundenEinstellungen,
    Kundengruppe,
    NotizVorlage,
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
    # Abschnitte für die Anzeige auf breiten Bildschirmen (Felder, die fehlen, entfallen)
    ABSCHNITTE = [
        ("Kunde", ["kundennummer", "status", "kundengruppe", "einkommensart"]),
        (
            "Haushalt und Termine",
            [
                "anzahl_erwachsene",
                "anzahl_kinder",
                "kunde_seit",
                "ausweis_gueltig_bis",
                "letzter_besuch",
            ],
        ),
        ("Anschrift und Kontakt", ["strasse", "plz", "ort", "telefon", "email"]),
    ]

    def abschnitte(self):
        """[(Titel, [Felder])]; Zusatzfelder der Tafel bilden einen eigenen Abschnitt."""
        ergebnis = [
            (titel, [self[n] for n in namen if n in self.fields])
            for titel, namen in self.ABSCHNITTE
        ]
        zusatz = [self[n] for n in self.fields if n.startswith("zusatz_")]
        if zusatz:
            ergebnis.append(("Weitere Angaben", zusatz))
        return [(titel, felder) for titel, felder in ergebnis if felder]

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
    staatsangehoerigkeit = forms.ChoiceField(
        label="Staatsangehörigkeit", required=False, widget=StaatAuswahl
    )

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
        self.fields["staatsangehoerigkeit"].choices = mit_vorhandenem(
            staatsangehoerigkeiten(), p.staatsangehoerigkeit
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
        fields = [
            "kuerzel", "name", "ausgabestelle", "wochentage", "uhrzeit", "maximum", "farbe",
            "aktiv",
        ]  # fmt: skip
        widgets = {"uhrzeit": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["wochentage"] = [
            t.strip() for t in (self.instance.wochentage or "").split(",") if t.strip()
        ]

    def clean_wochentage(self):
        return ", ".join(t for t in WOCHENTAGE if t in self.cleaned_data["wochentage"])


class AusgabestelleForm(forms.ModelForm):
    ABSCHNITTE = [
        ("Ausgabestelle", ["name", "aktiv"]),
        ("Anschrift", ["strasse", "plz", "ort"]),
        ("Kontakt und Anmerkungen", ["telefon", "email", "anmerkung"]),
        ("Ausweise", ["ausweise_hier"]),
    ]

    class Meta:
        model = Ausgabestelle
        fields = [
            "name",
            "aktiv",
            "strasse",
            "plz",
            "ort",
            "telefon",
            "email",
            "anmerkung",
            "ausweise_hier",
        ]
        widgets = {"anmerkung": forms.Textarea(attrs={"rows": 4})}

    def abschnitte(self):
        return [(t, [self[n] for n in namen]) for t, namen in self.ABSCHNITTE]


class UhrzeitEingabe(forms.TimeInput):
    input_type = "time"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%H:%M")


class AusgabestelleZeitForm(forms.ModelForm):
    art = forms.ChoiceField(label="Art", initial="Ausgabe")  # wie die Vorgabe im Modell

    class Meta:
        model = AusgabestelleZeit
        fields = ["wochentag", "von", "bis", "art", "hinweis"]
        widgets = {"von": UhrzeitEingabe(), "bis": UhrzeitEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["art"].choices = mit_vorhandenem([(a, a) for a in ZEITARTEN],
                                                     self.instance.art)  # fmt: skip

    def clean(self):
        daten = super().clean()
        if daten.get("von") and daten.get("bis") and daten["bis"] <= daten["von"]:
            self.add_error("bis", "„bis“ liegt nicht nach „von“.")
        return daten


class AusgabestelleKontaktForm(forms.ModelForm):
    zustaendigkeit = forms.ChoiceField(label="Zuständigkeit")

    class Meta:
        model = AusgabestelleKontakt
        fields = ["zustaendigkeit", "benutzer", "name", "telefon", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["zustaendigkeit"].choices = mit_vorhandenem(
            [("", "—")] + [(z, z) for z in ZUSTAENDIGKEITEN], self.instance.zustaendigkeit
        )  # leere Zeilen bleiben unverändert und werden übergangen
        konten = get_user_model().objects.filter(is_active=True)
        if self.instance.benutzer_id:  # gespeicherte Auswahl bleibt wählbar
            konten = konten | get_user_model().objects.filter(pk=self.instance.benutzer_id)
        self.fields["benutzer"].queryset = konten.order_by("last_name", "first_name", "username")
        self.fields["benutzer"].label_from_instance = lambda b: b.get_full_name() or b.username
        self.fields["benutzer"].empty_label = "— extern (Name eintragen) —"


ZeitenFormset = forms.inlineformset_factory(
    Ausgabestelle, AusgabestelleZeit, form=AusgabestelleZeitForm, extra=3, can_delete=True
)
KontakteFormset = forms.inlineformset_factory(
    Ausgabestelle, AusgabestelleKontakt, form=AusgabestelleKontaktForm, extra=2, can_delete=True
)


class EinkommensartForm(forms.ModelForm):
    class Meta:
        model = Einkommensart
        fields = ["bezeichnung", "aktiv"]


class DokumentartForm(forms.ModelForm):
    class Meta:
        model = Dokumentart
        fields = ["bezeichnung", "aufbewahren_monate", "aktiv"]


class HaushaltDokumentForm(forms.ModelForm):
    datei = forms.FileField(label="Datei (PDF oder Foto, höchstens 10 MB)")

    class Meta:
        model = HaushaltDokument
        fields = ["art", "titel", "datum"]
        widgets = {"datum": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["art"].queryset = Dokumentart.objects.filter(aktiv=True)
        self.fields["titel"].required = False
        self.fields["titel"].help_text = "Leer lassen: Name der Dokumentart."


class NotizVorlageForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        feld = self.fields["melden"]
        if self.instance.fest:
            # Darauf reagiert das Programm (Verlängerung, Ausweisdruck): Anliegen bleibt
            feld.disabled = True
            feld.help_text = ("Feste Vorlage: Der Text lässt sich ändern, das Anliegen nicht; "
                              "löschen geht nicht.")  # fmt: skip
            return
        # Nicht mehr angebotene Anliegen nur, wenn die Vorlage es schon hat; die festen
        # Anliegen haben ihre eigene Vorlage
        weg = (NACHRICHT_ANLIEGEN_ALT | set(FESTE_ANLIEGEN)) - {self.instance.melden}
        feld.choices = [c for c in feld.choices if c[0] not in weg]

    class Meta:
        model = NotizVorlage
        fields = ["text", "reihenfolge", "aktiv", "melden"]
        help_texts = {
            "text": "Erscheint am Einlass als Knopf; ein Klick speichert ihn als Notiz.",
            "reihenfolge": "Kleinere Zahlen stehen weiter vorn.",
        }


BILD_MAX_BYTES = 2 * 1024 * 1024


class AusweisVorlageForm(forms.ModelForm):
    """Einstellungen des Ausweises; die Elemente kommen als JSON aus dem Gestalter."""

    vorne = forms.CharField(widget=forms.HiddenInput, required=False)
    hinten = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = AusweisVorlage
        fields = ["name", "seitenformat", "rueckseite_aktiv", "hintergrund",
                  "hintergrund_rueckseite"]  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["vorne"] = json.dumps(self.instance.elemente_vorne())
        self.initial["hinten"] = json.dumps(self.instance.elemente_hinten())

    def _bild(self, name):
        bild = self.cleaned_data.get(name)
        if bild and getattr(bild, "size", 0) > BILD_MAX_BYTES:
            raise forms.ValidationError("Das Bild darf höchstens 2 MB groß sein.")
        return bild

    def clean_hintergrund(self):
        return self._bild("hintergrund")

    def clean_hintergrund_rueckseite(self):
        return self._bild("hintergrund_rueckseite")

    def _elemente(self, name):
        try:
            return json.loads(self.cleaned_data.get(name) or "[]")
        except ValueError:
            raise forms.ValidationError("Die Gestaltung war nicht lesbar.") from None

    def clean_vorne(self):
        from apps.kunden import ausweis

        return ausweis.elemente_pruefen(self._elemente("vorne"))

    def clean_hinten(self):
        from apps.kunden import ausweis

        return [e for e in map(ausweis.element_pruefen, self._elemente("hinten")) if e]

    def save(self, commit=True):
        self.instance.vorderseite = self.cleaned_data["vorne"]
        self.instance.rueckseite = self.cleaned_data["hinten"]
        return super().save(commit)
