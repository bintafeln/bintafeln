from django import forms

from apps.core.forms import Mehrfachauswahl
from apps.fahrdienst.forms import TageFeld
from apps.konten.forms import DatumEingabe
from apps.touren.models import Station, Tour, TourenEinstellungen, Warengruppe


class StationForm(forms.ModelForm):
    abholtage = TageFeld(label="Abholtage", required=False,
                         help_text="An diesen Wochentagen wird abgeholt.")  # fmt: skip

    class Meta:
        model = Station
        fields = [
            "name", "art", "kette", "filialnummer", "strasse", "hausnummer", "plz", "ort",
            "ortsteil", "telefon", "email", "email_lieferschein", "ansprechpartner",
            "oeffnungszeiten", "abholtage", "abholzeit", "anfahrt", "lieferschein", "aktiv",
            "kennung", "breite", "laenge", "notiz",
        ]  # fmt: skip
        widgets = {"anfahrt": forms.Textarea(attrs={"rows": 3}),
                   "notiz": forms.Textarea(attrs={"rows": 3})}  # fmt: skip

    def clean(self):
        daten = super().clean()
        if (daten.get("breite") is None) != (daten.get("laenge") is None):
            self.add_error("laenge", "Breiten- und Längengrad nur zusammen angeben.")
        return daten


def neue_kennung() -> str:
    """Kennung für eine von Hand angelegte Station: S-1, S-2 … (die nächste freie)."""
    nummern = [int(k[2:]) for k in Station.objects.filter(kennung__regex=r"^S-\d+$")
               .values_list("kennung", flat=True)]  # fmt: skip
    return f"S-{max(nummern, default=0) + 1}"


def waehlbare_personen():
    """Wer eine eigene oder kurzfristige Tour fahren kann: Fahrer, Beifahrer und Angestellte
    (Konto nicht gesperrt)."""
    from django.db.models import Q

    from apps.adressen.models import Adresse
    from apps.fahrdienst.forms import FAHRDIENST_ROLLEN

    return (Adresse.objects.filter(konto__is_active=True)
            .filter(Q(konto__groups__name__in=FAHRDIENST_ROLLEN) | Q(konto__beschaeftigung="fest"))
            .distinct().order_by("nachname", "vorname"))  # fmt: skip


class PersonenFeld(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class TourForm(forms.ModelForm):
    """Regelmäßige Tour: aus dem Fahrerplan oder eigene mit Fahrtagen und Personen."""

    fahrtage = TageFeld(
        label="Fahrtage", required=False,
        help_text="Nichts angehakt = an jedem Tag. Bei einer Tour aus dem Fahrerplan: an jedem "
        "Tag, an dem sie dort fährt – oder nur an den angehakten davon (z. B. die "
        "Montags-Reihenfolge).",
    )  # fmt: skip
    personen = PersonenFeld(
        queryset=None, required=False, label="Wer fährt",
        widget=Mehrfachauswahl(leer="niemand gewählt"),
        help_text="Nur für eigene Touren ohne Fahrerplan: Fahrer, Beifahrer und Angestellte.",
    )  # fmt: skip

    class Meta:
        model = Tour
        fields = ["name", "fahrdienst_tour", "fahrtage", "personen", "hinweis", "aktiv"]
        widgets = {"hinweis": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, fahrdienst=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["personen"].queryset = waehlbare_personen()
        if fahrdienst:
            from apps.fahrdienst.models import Tour as FahrdienstTour

            self.fields["fahrdienst_tour"].queryset = FahrdienstTour.objects.filter(aktiv=True)
            self.fields["fahrdienst_tour"].empty_label = "– eigene Tour, nicht im Fahrerplan –"
        else:
            del self.fields["fahrdienst_tour"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        gleiche = Tour.objects.filter(datum__isnull=True, name__iexact=name)
        if gleiche.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Eine Tour mit diesem Namen gibt es schon.")
        return name


class KurzfristigForm(forms.ModelForm):
    """Kurzfristige Tour für einen Tag, mit eigenen Personen."""

    personen = PersonenFeld(
        queryset=None, required=False, label="Wer fährt",
        widget=Mehrfachauswahl(leer="niemand gewählt"),
        help_text="Fahrer, Beifahrer und Angestellte. Sie bekommen die Tour mit „An die Fahrer "
        "schicken“ per E-Mail.",
    )  # fmt: skip

    class Meta:
        model = Tour
        fields = ["name", "datum", "personen", "hinweis", "aktiv"]
        widgets = {"hinweis": forms.Textarea(attrs={"rows": 2}), "datum": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["personen"].queryset = waehlbare_personen()
        self.fields["datum"].required = True
        self.fields["datum"].label = "Am"
        self.fields["datum"].help_text = ""


class HaltForm(forms.Form):
    station = forms.ModelChoiceField(
        queryset=None, label="Station anhängen", empty_label="– Station wählen –")  # fmt: skip

    def __init__(self, *args, tour, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["station"].queryset = Station.objects.filter(aktiv=True).exclude(
            halte__tour=tour)  # fmt: skip


class EinstellungenForm(forms.ModelForm):
    class Meta:
        model = TourenEinstellungen
        fields = ["lieferscheine", "versand", "test_email", "mail_text", "aufbewahrung_jahre"]
        widgets = {
            "mail_text": forms.Textarea(attrs={"rows": 5}),
            "test_email": forms.EmailInput(attrs={"data-zeigen-bei": "versand=test"}),
        }

    def clean(self):
        daten = super().clean()
        if daten.get("versand") == TourenEinstellungen.Versand.TEST and not daten.get("test_email"):
            self.add_error("test_email", "Für den Testbetrieb bitte eine Adresse eintragen.")
        return daten


WarengruppenFormSet = forms.modelformset_factory(
    Warengruppe, fields=["name", "reihenfolge", "aktiv"], extra=2, can_delete=False
)
