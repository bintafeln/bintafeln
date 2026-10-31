from django import forms

from apps.adressen.models import Adresse
from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import geheimnis
from apps.core.auswahl import FAHRDIENST_AUSFALLGRUENDE
from apps.dienstplan.models import (
    Aufgabe,
    Ausfall,
    DienstplanEinstellungen,
    DienstStelle,
    Diensttag,
)
from apps.konten.forms import DatumEingabe


class TageFeld(forms.MultipleChoiceField):
    """Wochentage als Häkchen, gespeichert als „Mo, Mi“."""

    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        super().__init__(choices=[(t, t) for t in WOCHENTAGE], **kwargs)

    def prepare_value(self, value):
        return wochentage(value) if isinstance(value, str) else value

    def clean(self, value):
        gewaehlt = super().clean(value)
        return ", ".join(t for t in WOCHENTAGE if t in gewaehlt)


class HelferWahl(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name


def helfer_aktiv():
    """Die aktiven Helfer aus dem Adressbuch (ADR 0097)."""
    return (Adresse.objects.filter(helfer=True, helfer_aktiv=True)
            .order_by("nachname", "vorname"))  # fmt: skip


class EinstellungenForm(forms.ModelForm):
    telegram_schluessel = forms.CharField(
        label="Telegram: Bot-Schlüssel", required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Leer lassen = unverändert. Von @BotFather; verschlüsselt gespeichert.",
    )  # fmt: skip

    class Meta:
        model = DienstplanEinstellungen
        fields = ["selbst_melden", "feiertage_frei", "aufbewahren_monate", "telegram_chats"]

    def save(self, commit=True):
        e = super().save(commit=False)
        if self.cleaned_data.get("telegram_schluessel", "").strip():
            e.telegram_schluessel_verschluesselt = geheimnis.verschluesseln(
                self.cleaned_data["telegram_schluessel"].strip()
            )
        if commit:
            e.save()
        return e


class StelleForm(forms.ModelForm):
    tage = TageFeld(label="Ausgabetage", required=False)

    class Meta:
        model = DienstStelle
        fields = ["aktiv", "tage"]


class DiensttagForm(forms.ModelForm):
    teamleitung = HelferWahl(label="Teamleitung", queryset=helfer_aktiv(), required=False,
                             help_text="Bekommt Ausfälle dieses Tages per E-Mail.")  # fmt: skip

    class Meta:
        model = Diensttag
        fields = ["teamleitung", "telefon"]


class AufgabeForm(forms.ModelForm):
    class Meta:
        model = Aufgabe
        fields = ["name", "von", "bis", "reihenfolge", "pflicht"]
        widgets = {"von": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
                   "bis": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}  # fmt: skip
        help_texts = {"reihenfolge": "Leer = ans Ende."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reihenfolge"].required = False

    def clean_reihenfolge(self):
        return self.cleaned_data.get("reihenfolge") or 0


class AusfallForm(forms.ModelForm):
    """Wer fällt aus? Wer plant, wählt die Person; sonst der eigene Helfer-Eintrag."""

    helfer = HelferWahl(label="Wer fällt aus?", queryset=helfer_aktiv())
    dauer = forms.TypedChoiceField(
        label="Wie lange?", coerce=int, required=False, empty_value=1,
        choices=[(1, "nur dieser Tag"), (7, "1 Woche"), (14, "2 Wochen"), (21, "3 Wochen"),
                 (28, "4 Wochen")],
        help_text="Oder unten ein genaues Ende eintragen.",
    )  # fmt: skip

    class Meta:
        model = Ausfall
        fields = ["helfer", "von", "dauer", "bis", "grund", "anmerkung"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}
        labels = {"von": "Ab", "bis": "Bis (genau)"}
        help_texts = {"bis": "Leer = so lange wie oben gewählt."}

    def __init__(self, *args, planen=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bis"].required = False
        self.fields["grund"].choices = FAHRDIENST_AUSFALLGRUENDE
        if not planen:
            del self.fields["helfer"]

    def clean(self):
        import datetime as dt

        daten = super().clean()
        von, bis = daten.get("von"), daten.get("bis")
        if von and not bis:
            daten["bis"] = von + dt.timedelta(days=(daten.get("dauer") or 1) - 1)
        elif von and bis and bis < von:
            self.add_error("bis", "Das Ende liegt vor dem Anfang.")
        return daten
