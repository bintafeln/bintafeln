import datetime as dt

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

    telegram_schluessel = forms.CharField(
        label="Telegram: Bot-Schlüssel", required=False, widget=forms.PasswordInput,
        help_text="Von @BotFather in Telegram („/newbot“). Wird verschlüsselt gespeichert; leer "
        "lassen = bleibt wie er ist.",
    )  # fmt: skip
    telegram_schluessel_loeschen = forms.BooleanField(
        label="Gespeicherten Bot-Schlüssel löschen", required=False
    )

    class Meta:
        model = FahrdienstEinstellungen
        fields = ["selbst_melden", "benachrichtigen", "fahrtage", "feiertage_frei",
                  "aufbewahren_monate", "telegram_chats"]  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["benachrichtigen"].label_from_instance = lambda b: (
            f"{b.get_full_name() or b.username} ({b.email})"
        )
        if self.instance.telegram_schluessel_verschluesselt:
            self.fields["telegram_schluessel"].help_text = (
                "Ein Schlüssel ist gespeichert. " + self.fields["telegram_schluessel"].help_text
            )
        else:
            del self.fields["telegram_schluessel_loeschen"]

    def save(self, commit=True):
        from apps.core import geheimnis

        e = super().save(commit=False)
        if self.cleaned_data.get("telegram_schluessel_loeschen"):
            e.telegram_schluessel_verschluesselt = ""
        elif self.cleaned_data.get("telegram_schluessel"):
            e.telegram_schluessel_verschluesselt = geheimnis.verschluesseln(
                self.cleaned_data["telegram_schluessel"].strip()
            )
        if commit:
            e.save()
            self.save_m2m()
        return e


class TourForm(forms.ModelForm):
    class Meta:
        model = Tour
        fields = ["name", "reihenfolge", "plaetze", "mindestbesetzung", "aktiv"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mindestbesetzung"].required = False  # leer = 2 (höchstens alle Plätze)

    def clean(self):
        daten = super().clean()
        plaetze, mindest = daten.get("plaetze"), daten.get("mindestbesetzung")
        if plaetze and not mindest:
            daten["mindestbesetzung"] = mindest = min(2, plaetze)
        if plaetze and mindest and mindest > plaetze:
            self.add_error("mindestbesetzung", "Mehr als die Zahl der Plätze geht nicht.")
        return daten


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
    dauer = forms.TypedChoiceField(
        label="Wie lange?", coerce=int, required=False, empty_value=1,
        choices=[(1, "nur dieser Tag"), (7, "1 Woche"), (14, "2 Wochen"), (21, "3 Wochen"),
                 (28, "4 Wochen")],
        help_text="Oder unten ein genaues Ende eintragen.",
    )  # fmt: skip

    class Meta:
        model = Ausfall
        fields = ["benutzer", "von", "dauer", "bis", "grund", "anmerkung"]
        widgets = {"von": DatumEingabe(), "bis": DatumEingabe()}
        labels = {"von": "Ab", "bis": "Bis (genau)"}
        help_texts = {"bis": "Leer = so lange wie oben gewählt."}

    def __init__(self, *args, planen=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bis"].required = False
        if not planen:
            del self.fields["benutzer"]

    def clean(self):
        daten = super().clean()
        von, bis = daten.get("von"), daten.get("bis")
        if von and not bis:
            daten["bis"] = von + dt.timedelta(days=(daten.get("dauer") or 1) - 1)
        elif von and bis and bis < von:
            self.add_error("bis", "Das Ende liegt vor dem Anfang.")
        return daten
