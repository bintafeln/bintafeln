from django import forms
from django.utils import timezone

from apps.fahrdienst.forms import TageFeld
from apps.konten.forms import DatumEingabe
from apps.touren.models import (
    Fahrzeug,
    FahrzeugDokument,
    Kurztext,
    Station,
    Tour,
    TourenEinstellungen,
    Umstand,
    Warengruppe,
)


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.ausgabestelle_id:
            # Diese Angaben kommen aus der Ausgabestelle und werden dort geändert (ADR 0171)
            from apps.touren.ausgabestellen import FELDER

            for name in (*FELDER, "art", "kennung"):
                self.fields[name].disabled = True
                self.fields[name].help_text = "Kommt aus der Ausgabestelle."

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


class PersonFeld(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class BesetzungMixin:
    """Fahrer, Beifahrer, zweiter Beifahrer und Gast einer eigenen oder kurzfristigen Tour
    (ADR 0153). ``Tour.personen`` folgt daraus: alle, die mitfahren."""

    PLAETZE = ("fahrer", "beifahrer", "beifahrer2")

    def besetzung_einrichten(self):
        for name in self.PLAETZE:
            self.fields[name].queryset = waehlbare_personen()
            self.fields[name].empty_label = "– offen –"

    def clean(self):
        daten = super().clean()
        gewaehlt = [daten.get(n) for n in self.PLAETZE if daten.get(n)]
        if len({p.pk for p in gewaehlt}) != len(gewaehlt):
            raise forms.ValidationError("Jede Person kann nur auf einem Platz fahren.")
        return daten

    def _save_m2m(self):
        super()._save_m2m()
        tour = self.instance
        tour.personen.set([p for p in (tour.fahrer, tour.beifahrer, tour.beifahrer2) if p])


def _platz(label, hilfe=""):
    return PersonFeld(queryset=None, required=False, label=label, help_text=hilfe)


class TourForm(BesetzungMixin, forms.ModelForm):
    """Regelmäßige Tour: aus dem Fahrerplan oder eigene mit Fahrtagen und Personen."""

    fahrtage = TageFeld(
        label="Fahrtage", required=False,
        help_text="Nichts angehakt = an jedem Tag. Bei einer Tour aus dem Fahrerplan: an jedem "
        "Tag, an dem sie dort fährt – oder nur an den angehakten davon (z. B. die "
        "Montags-Reihenfolge).",
    )  # fmt: skip
    fahrer = _platz("Fahrer/in", "Nur für eigene Touren; bei einer Tour aus dem Fahrerplan "
                    "steht die Besetzung dort.")  # fmt: skip
    beifahrer = _platz("Beifahrer/in")
    beifahrer2 = _platz("2. Beifahrer/in")

    class Meta:
        model = Tour
        fields = ["name", "fahrdienst_tour", "fahrtage", "fahrer", "beifahrer", "beifahrer2",
                  "gast", "hinweis", "aktiv"]  # fmt: skip
        widgets = {"hinweis": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, fahrdienst=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.besetzung_einrichten()
        if fahrdienst:
            from apps.fahrdienst.models import Tour as FahrdienstTour

            self.fields["fahrdienst_tour"].queryset = FahrdienstTour.objects.filter(aktiv=True)
            self.fields["fahrdienst_tour"].empty_label = "– eigene Tour, nicht im Fahrerplan –"
            # Bei einer Tour aus dem Fahrerplan steht die Besetzung dort (oben auf der Seite). Die
            # eigenen Plätze blieben leer stehen und sähen aus, als fehlten die Fahrer – deshalb
            # nur zeigen, solange keine Tour im Fahrerplan gewählt ist (zeigen_bei.js).
            for name in (*self.PLAETZE, "gast"):
                self.fields[name].widget.attrs["data-zeigen-bei"] = "fahrdienst_tour="
        else:
            del self.fields["fahrdienst_tour"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        gleiche = Tour.objects.filter(datum__isnull=True, name__iexact=name)
        if gleiche.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Eine Tour mit diesem Namen gibt es schon.")
        return name


class KurzfristigForm(BesetzungMixin, forms.ModelForm):
    """Kurzfristige Tour für einen Tag, mit eigener Besetzung."""

    fahrer = _platz("Fahrer/in", "Wer mitfährt, bekommt die Tour mit „An die Fahrer schicken“ "
                    "per E-Mail.")  # fmt: skip
    beifahrer = _platz("Beifahrer/in")
    beifahrer2 = _platz("2. Beifahrer/in")

    class Meta:
        model = Tour
        fields = ["name", "datum", "fahrer", "beifahrer", "beifahrer2", "gast", "hinweis",
                  "aktiv"]  # fmt: skip
        widgets = {"hinweis": forms.Textarea(attrs={"rows": 2}), "datum": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.besetzung_einrichten()
        self.fields["datum"].required = True
        self.fields["datum"].label = "Am"
        self.fields["datum"].help_text = ""


class MannschaftForm(BesetzungMixin, forms.ModelForm):
    """Am Tag selbst, vom Handy: Wer fährt die kurzfristige Tour wirklich? Die Mannschaft ändert
    oder ergänzt ihre Besetzung selbst (Mitfahrer, Gast)."""

    fahrer = _platz("Fahrer/in")
    beifahrer = _platz("Beifahrer/in")
    beifahrer2 = _platz("2. Beifahrer/in")

    class Meta:
        model = Tour
        fields = ["fahrer", "beifahrer", "beifahrer2", "gast"]

    def __init__(self, *args, wer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.wer = wer  # Adresse der Person, die ändert; None = darf jede Besetzung eintragen
        self.besetzung_einrichten()
        self.fields["gast"].label = "Gast ohne Konto"
        self.fields[
            "gast"
        ].help_text = "Vor- und Nachname, wenn jemand ohne eigenes Konto mitfährt."

    def clean(self):
        daten = super().clean()
        gewaehlt = {daten[n].pk for n in self.PLAETZE if daten.get(n)}
        if self.wer is not None and self.wer.pk not in gewaehlt:
            raise forms.ValidationError(
                "Sie können sich nicht selbst aus der Tour nehmen. Bitte im Büro melden."
            )
        return daten


class NeueStationForm(forms.ModelForm):
    """Eine Station, die noch nicht in der Liste steht, gleich in der Maske der kurzfristigen
    Tour eintragen. Leer gelassen = keine neue Station."""

    # Die Felder stehen eingeklappt in der Maske der Tour und dürfen leer bleiben; der Browser
    # darf das Absenden deshalb nicht an ihnen aufhalten. Geprüft wird im Server.
    use_required_attribute = False

    class Meta:
        model = Station
        fields = ["name", "art", "strasse", "hausnummer", "plz", "ort", "telefon",
                  "ansprechpartner", "anfahrt"]  # fmt: skip
        widgets = {"anfahrt": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["art"].initial = Station.Art.SONSTIGES
        for feld in self.fields.values():
            feld.help_text = ""

    def ausgefuellt(self) -> bool:
        """Wurde überhaupt etwas eingetragen (außer der vorbelegten Art)?"""
        return self.is_bound and any(
            (self.data.get(self.add_prefix(name)) or "").strip()
            for name in self.fields if name != "art"
        )  # fmt: skip

    def anlegen(self, von: str) -> Station:
        station = self.save(commit=False)
        station.kennung = neue_kennung()
        station.geaendert_am, station.geaendert_von = timezone.now(), von
        station.save()
        return station


class HaltForm(forms.Form):
    station = forms.ModelChoiceField(
        queryset=None, label="Station anhängen", empty_label="– Station wählen –")  # fmt: skip

    def __init__(self, *args, tour, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["station"].queryset = Station.objects.filter(aktiv=True).exclude(
            halte__tour=tour)  # fmt: skip


class EinstellungenForm(forms.ModelForm):
    eco_adresse = forms.URLField(label="Adresse der ECO-Plattform", required=False,
                                 assume_scheme="https")  # fmt: skip

    karten_schluessel = forms.CharField(
        label="Google-Schlüssel für die Karte in der Tourenplanung", required=False,
        widget=forms.PasswordInput,
        help_text="Schlüssel der „Maps Embed API“ aus der Google-Cloud (kostenlos). Damit zeigt "
        "die Tourenplanung die Route als Karte in der Seite; ohne Schlüssel gibt es einen Knopf, "
        "der die Route in einem eigenen Fenster öffnet. Wird verschlüsselt gespeichert; leer "
        "lassen = bleibt wie er ist.",
    )  # fmt: skip
    karten_schluessel_loeschen = forms.BooleanField(
        label="Gespeicherten Google-Schlüssel löschen", required=False
    )

    class Meta:
        model = TourenEinstellungen
        fields = ["lieferscheine", "versand", "test_email", "aufbewahrung_jahre",
                  "eco_plattform", "eco_adresse"]  # fmt: skip
        widgets = {"test_email": forms.EmailInput(attrs={"data-zeigen-bei": "versand=test"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.karten_schluessel_verschluesselt:
            self.fields["karten_schluessel"].help_text = (
                "Ein Schlüssel ist gespeichert. " + self.fields["karten_schluessel"].help_text
            )
        else:
            del self.fields["karten_schluessel_loeschen"]

    def save(self, commit=True):
        from apps.core import geheimnis

        e = super().save(commit=False)
        if self.cleaned_data.get("karten_schluessel_loeschen"):
            e.karten_schluessel_verschluesselt = ""
        elif self.cleaned_data.get("karten_schluessel"):
            e.karten_schluessel_verschluesselt = geheimnis.verschluesseln(
                self.cleaned_data["karten_schluessel"].strip()
            )
        if commit:
            e.save()
        return e

    def clean(self):
        daten = super().clean()
        if daten.get("versand") == TourenEinstellungen.Versand.TEST and not daten.get("test_email"):
            self.add_error("test_email", "Für den Testbetrieb bitte eine Adresse eintragen.")
        return daten


class EinrichtenForm(forms.ModelForm):
    """Was die Fahrdienstleitung selbst einrichtet (Menü „Touren → Einrichten“)."""

    class Meta:
        model = TourenEinstellungen
        fields = ["zentrale", "zentrale_aus", "kiste_kg", "mail_text"]
        localized_fields = ["kiste_kg"]  # „8,5“ mit Komma
        widgets = {"mail_text": forms.Textarea(attrs={"rows": 5})}


class FahrzeugForm(forms.ModelForm):
    """Ein Fahrzeug anlegen oder ändern (eigene Seite je Fahrzeug)."""

    class Meta:
        model = Fahrzeug
        fields = ["name", "kennzeichen", "typ", "erstzulassung", "kilometerstand", "reihenfolge",
                  "aktiv", "verkauft_am"]  # fmt: skip
        widgets = {
            "erstzulassung": DatumEingabe(),
            "verkauft_am": DatumEingabe(),
            "typ": forms.TextInput(attrs={"list": "fz-arten", "autocomplete": "off"}),
        }
        help_texts = {"reihenfolge": "Kleinere Zahl = weiter oben in der Auswahl der Fahrer.",
                      "aktiv": "Ausschalten, wenn das Fahrzeug nicht mehr gefahren wird; im "
                               "Fahrtenbuch bleibt es stehen."}  # fmt: skip

    def clean(self):
        daten = super().clean()
        zugelassen, verkauft = daten.get("erstzulassung"), daten.get("verkauft_am")
        if zugelassen and verkauft and verkauft < zugelassen:
            self.add_error("verkauft_am", "Der Verkauf kann nicht vor der Erstzulassung liegen.")
        return daten


class FahrzeugDokumentForm(forms.ModelForm):
    datei = forms.FileField(label="Datei", help_text="Foto (JPG, PNG, WebP) oder PDF, bis 10 MB.")

    class Meta:
        model = FahrzeugDokument
        fields = ["art", "bezeichnung"]
        widgets = {"bezeichnung": forms.TextInput(attrs={"data-zeigen-bei": "art=sonstiges"})}


UmstaendeFormSet = forms.modelformset_factory(
    Umstand,
    fields=["name", "reihenfolge", "anmerkung_pflicht", "aktiv"],
    extra=2,
    can_delete=False,
)

KurztexteFormSet = forms.modelformset_factory(
    Kurztext,
    fields=["text", "reihenfolge", "aktiv"],
    extra=2,
    can_delete=False,
)

WarengruppenFormSet = forms.modelformset_factory(
    Warengruppe,
    fields=["name", "reihenfolge", "kiste_kg", "aktiv"],
    extra=2,
    can_delete=False,
    localized_fields=["kiste_kg"],
)
