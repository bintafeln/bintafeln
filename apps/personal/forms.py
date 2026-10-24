import datetime as dt

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.konten.forms import DatumEingabe
from apps.personal import arbeitszeit
from apps.personal.models import (
    Abwesenheit,
    Arbeitsvertrag,
    ArbeitszeitEinstellungen,
    Stunden,
    Urlaubsjahr,
    Zeitbuchung,
)


class VertragForm(forms.ModelForm):
    class Meta:
        model = Arbeitsvertrag
        fields = [
            "beginn", "ende", "taetigkeit", "wochenstunden", "urlaubstage", "stundenlohn",
            "bemerkung",
        ]  # fmt: skip
        widgets = {
            "beginn": DatumEingabe(),
            "ende": DatumEingabe(),
            "bemerkung": forms.Textarea(attrs={"rows": 2}),
        }
        localized_fields = ["wochenstunden", "urlaubstage", "stundenlohn"]


class AbwesenheitForm(forms.ModelForm):
    class Meta:
        model = Abwesenheit
        fields = ["art", "von", "bis", "tage", "au_vorgelegt", "bemerkung"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}
        localized_fields = ["tage"]


class UrlaubsjahrForm(forms.ModelForm):
    class Meta:
        model = Urlaubsjahr
        fields = ["anspruch", "verfall_am"]
        widgets = {"verfall_am": DatumEingabe()}
        localized_fields = ["anspruch"]


class StundenForm(forms.ModelForm):
    class Meta:
        model = Stunden
        fields = ["datum", "stunden", "bemerkung"]
        widgets = {"datum": DatumEingabe()}
        localized_fields = ["stunden"]


class UhrzeitEingabe(forms.TimeInput):
    input_type = "time"

    def __init__(self, **kwargs):
        super().__init__(format="%H:%M", **kwargs)


class ZeitbuchungForm(forms.Form):
    """Nachtragen oder Korrigieren einer Zeitbuchung durch das Personal."""

    datum = forms.DateField(label="Datum", widget=DatumEingabe())
    kommen = forms.TimeField(label="Kommen", widget=UhrzeitEingabe())
    gehen = forms.TimeField(
        label="Gehen", required=False, widget=UhrzeitEingabe(), help_text="Leer = noch offen."
    )
    bemerkung = forms.CharField(
        label="Grund der Korrektur", max_length=200, help_text="z. B. „Gehen vergessen“."
    )

    def __init__(self, data=None, *, buchung: Zeitbuchung, **kwargs):
        self.buchung = buchung
        if buchung.pk and data is None:
            beginn = timezone.localtime(buchung.beginn)
            kwargs["initial"] = {
                "datum": beginn.date(),
                "kommen": beginn.time(),
                "gehen": timezone.localtime(buchung.ende).time() if buchung.ende else None,
                "bemerkung": buchung.bemerkung,
            }
        super().__init__(data, **kwargs)

    def clean(self):
        daten = super().clean()
        if self.errors:
            return daten
        zeitzone = timezone.get_current_timezone()
        b = self.buchung
        b.beginn = dt.datetime.combine(daten["datum"], daten["kommen"], zeitzone)
        gehen = daten.get("gehen")
        b.ende = dt.datetime.combine(daten["datum"], gehen, zeitzone) if gehen else None
        b.bemerkung = daten["bemerkung"]
        try:
            b.clean()
        except ValidationError as fehler:
            raise ValidationError(fehler.message_dict["ende"]) from None
        andere = arbeitszeit.ueberschneidung(b)
        if andere:
            raise ValidationError(f"Überschneidet sich mit der Buchung {andere}.")
        return daten


class ArbeitszeitEinstellungenForm(forms.ModelForm):
    class Meta:
        model = ArbeitszeitEinstellungen
        fields = ["ehrenamtliche_stempeln", "pausen_automatisch", "offen_hoechstens_stunden"]
