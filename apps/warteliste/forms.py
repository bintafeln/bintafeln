from django import forms

from apps.konten.forms import DatumEingabe
from apps.kunden.forms_bearbeiten import UhrzeitEingabe
from apps.kunden.models import Zusatzfeld
from apps.warteliste.models import PLATZHALTER, Termin, WartelisteEinstellungen, Wartestand

S = Wartestand.Status
# Was das Team von Hand setzen kann („neu“, „eingeladen“ und „aufgenommen“ entstehen von selbst)
STATUS_HAND = [(s.value, s.label) for s in (S.WARTEND, S.WARTEZEIT, S.ERSCHIENEN, S.ENTSCHULDIGT,
                                            S.STREICHEN_MOEGLICH, S.GESTRICHEN)]  # fmt: skip


class TerminForm(forms.ModelForm):
    class Meta:
        model = Termin
        fields = ["datum", "von", "bis", "ort", "anmerkung"]
        widgets = {"datum": DatumEingabe(), "von": UhrzeitEingabe(), "bis": UhrzeitEingabe(),
                   "ort": forms.Textarea(attrs={"rows": 3})}  # fmt: skip

    def clean(self):
        daten = super().clean()
        if daten.get("von") and daten.get("bis") and daten["bis"] <= daten["von"]:
            self.add_error("bis", "„bis“ muss nach „von“ liegen.")
        return daten


class EinladenForm(forms.Form):
    """Ausgewählte Anträge zu einem vorhandenen oder neuen Termin einladen."""

    termin = forms.ModelChoiceField(Termin.objects.none(), label="Termin", required=False,
                                    empty_label="– neuer Termin –")  # fmt: skip
    datum = forms.DateField(label="Datum (neuer Termin)", required=False, widget=DatumEingabe())
    von = forms.TimeField(label="von", required=False, widget=UhrzeitEingabe())
    bis = forms.TimeField(label="bis", required=False, widget=UhrzeitEingabe())
    mail = forms.BooleanField(
        label="Einladung per E-Mail senden", required=False, initial=True,
        help_text="Ohne E-Mail-Adresse oder ohne Haken: nur eintragen, dann bitte anrufen oder "
        "einen Brief schicken.",
    )  # fmt: skip

    def __init__(self, *args, termine=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["termin"].queryset = termine if termine is not None else Termin.objects.all()

    def clean(self):
        daten = super().clean()
        if not daten.get("termin"):
            if not daten.get("datum") or not daten.get("von"):
                raise forms.ValidationError("Bitte einen Termin wählen oder Datum und Uhrzeit "
                                            "für einen neuen Termin angeben.")  # fmt: skip
            if daten.get("bis") and daten["bis"] <= daten["von"]:
                self.add_error("bis", "„bis“ muss nach „von“ liegen.")
        return daten

    def termin_holen(self) -> Termin:
        d = self.cleaned_data
        if d.get("termin"):
            return d["termin"]
        termin, _ = Termin.objects.get_or_create(datum=d["datum"], von=d["von"],
                                                 defaults={"bis": d.get("bis")})  # fmt: skip
        return termin


class StatusForm(forms.Form):
    status = forms.ChoiceField(label="Neuer Status", choices=STATUS_HAND)
    wartezeit_bis = forms.DateField(label="Wartezeit bis", required=False, widget=DatumEingabe(),
                                    help_text="Nur für „Wartezeit“.")  # fmt: skip

    def clean(self):
        daten = super().clean()
        if daten.get("status") == S.WARTEZEIT and not daten.get("wartezeit_bis"):
            self.add_error("wartezeit_bis", "Für „Wartezeit“ bitte das Datum angeben.")
        return daten


class EinstellungenForm(forms.ModelForm):
    ABSCHNITTE = [
        ("Fristen", ["streichen_nach_tagen", "automatik", "streichungsliste_tage"]),
        ("Sperrzeit für frühere Kunden", ["sperrzeit_monate", "ausnahme_ab_alter",
                                          "ausnahme_feld"]),
        ("Einladung", ["ort", "betreff", "anrede", "einleitung", "schluss", "mitbringen", "gruss"]),
        ("Absage", ["absage_betreff", "absage_text"]),
    ]  # fmt: skip

    class Meta:
        model = WartelisteEinstellungen
        fields = ["streichen_nach_tagen", "automatik", "streichungsliste_tage", "sperrzeit_monate",
                  "ausnahme_ab_alter", "ausnahme_feld", "ort", "betreff", "anrede", "einleitung",
                  "schluss", "mitbringen", "gruss", "absage_betreff", "absage_text"]  # fmt: skip
        widgets = {
            f: forms.Textarea(attrs={"rows": 3})
            for f in ["ort", "einleitung", "schluss", "mitbringen", "gruss", "absage_text"]
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        feld = self.fields["ausnahme_feld"]
        feld.queryset = Zusatzfeld.objects.filter(typ=Zusatzfeld.Typ.JA_NEIN, aktiv=True)
        feld.empty_label = "– keines –"
        for name in ["betreff", "anrede", "einleitung", "schluss", "gruss", "absage_betreff",
                     "absage_text"]:  # fmt: skip
            self.fields[name].help_text = f"Platzhalter: {PLATZHALTER}"

    def abschnitte(self):
        return [(titel, [self[f] for f in felder]) for titel, felder in self.ABSCHNITTE]
