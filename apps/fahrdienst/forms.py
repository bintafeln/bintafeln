from django import forms
from django.contrib.auth import get_user_model

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.fahrdienst.models import Ausfall, FahrdienstEinstellungen, Springer, Tour
from apps.konten.forms import DatumEingabe


class Person(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.username


def aktive():
    return (
        get_user_model()
        .objects.filter(is_active=True)
        .order_by("last_name", "first_name", "username")
    )


class TageFeld(forms.MultipleChoiceField):
    """Wochentage als Häkchen, gespeichert als „Mo, Mi“ (wie bei den Kundengruppen)."""

    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        super().__init__(choices=[(t, t) for t in WOCHENTAGE], **kwargs)

    def prepare_value(self, value):
        return wochentage(value) if isinstance(value, str) else value

    def clean(self, value):
        gewaehlt = super().clean(value)
        return ", ".join(t for t in WOCHENTAGE if t in gewaehlt)


class EinstellungenForm(forms.ModelForm):
    fahrtage = TageFeld(label="Fahrtage")
    benachrichtigen = forms.ModelMultipleChoiceField(
        label="Bei einem Ausfall benachrichtigen", queryset=aktive().exclude(email=""),
        required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Per E-Mail; zur Auswahl stehen Konten mit E-Mail-Adresse. Leer = alle, die "
        "den Fahrdienst planen dürfen.",
    )  # fmt: skip

    class Meta:
        model = FahrdienstEinstellungen
        fields = ["selbst_melden", "benachrichtigen", "fahrtage", "feiertage_frei",
                  "aufbewahren_monate"]  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["benachrichtigen"].label_from_instance = lambda b: (
            f"{b.get_full_name() or b.username} ({b.email})"
        )


class TourForm(forms.ModelForm):
    class Meta:
        model = Tour
        fields = ["name", "reihenfolge", "plaetze", "aktiv"]


class SpringerForm(forms.ModelForm):
    benutzer = Person(label="Person", queryset=aktive())
    wochentage = TageFeld(label="Nur an diesen Tagen", required=False,
                          help_text="Keiner gewählt = an allen Fahrtagen.")  # fmt: skip

    class Meta:
        model = Springer
        fields = ["benutzer", "wochentage", "anmerkung"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        schon = Springer.objects.exclude(pk=self.instance.pk).values_list("benutzer", flat=True)
        self.fields["benutzer"].queryset = aktive().exclude(pk__in=schon)


class AusfallForm(forms.ModelForm):
    """Wer fällt aus? Wer plant, wählt die Person; sonst ist es das eigene Konto."""

    benutzer = Person(label="Wer fällt aus?", queryset=aktive())

    class Meta:
        model = Ausfall
        fields = ["benutzer", "von", "bis", "grund", "anmerkung"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}
        help_texts = {"bis": "Leer = nur der eine Tag."}

    def __init__(self, *args, planen=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bis"].required = False
        if not planen:
            del self.fields["benutzer"]

    def clean(self):
        daten = super().clean()
        von, bis = daten.get("von"), daten.get("bis")
        if von and not bis:
            daten["bis"] = von
        elif von and bis and bis < von:
            self.add_error("bis", "Das Ende liegt vor dem Anfang.")
        return daten
