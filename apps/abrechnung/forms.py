from django import forms

from apps.abrechnung.models import AbrechnungEinstellungen, Posten
from apps.konten.forms import DatumEingabe

QUITTUNG_TYPEN = "image/*,application/pdf"


class PostenForm(forms.ModelForm):
    art = forms.ChoiceField(label="Art")
    foto = forms.FileField(
        label="Quittung fotografieren", required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*", "capture": "environment"}),
    )  # fmt: skip
    datei = forms.FileField(
        label="oder Datei wählen (Foto oder PDF, höchstens 10 MB)", required=False,
        widget=forms.ClearableFileInput(attrs={"accept": QUITTUNG_TYPEN}),
    )  # fmt: skip

    class Meta:
        model = Posten
        fields = ["datum", "betrag", "art", "empfaenger", "anmerkung"]
        widgets = {"datum": DatumEingabe()}
        localized_fields = ["betrag"]  # „12,50“ wie gewohnt

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        arten = list(AbrechnungEinstellungen.laden().arten or [])
        self.fields["art"].choices = [("", "– bitte wählen –"), *((a, a) for a in arten)]

    @property
    def quittung(self):
        return self.cleaned_data.get("foto") or self.cleaned_data.get("datei")


class EinreichenForm(forms.Form):
    anmerkung = forms.CharField(label="Anmerkung für das Büro", required=False,
                                widget=forms.Textarea(attrs={"rows": 2}))  # fmt: skip


class RueckgabeForm(forms.Form):
    grund = forms.CharField(label="Was ist noch zu ändern?", max_length=300)


class EinstellungenForm(forms.ModelForm):
    arten_text = forms.CharField(
        label="Arten der Ausgaben", widget=forms.Textarea(attrs={"rows": 8}),
        help_text="Eine Art je Zeile, in der Reihenfolge der Auswahl. Bereits erfasste Ausgaben "
        "behalten ihre Art.",
    )  # fmt: skip

    class Meta:
        model = AbrechnungEinstellungen
        fields = ["aufbewahrung_jahre"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["arten_text"] = "\n".join(self.instance.arten or [])

    def clean_arten_text(self):
        arten = []
        for zeile in self.cleaned_data["arten_text"].splitlines():
            zeile = zeile.strip()[:80]
            if zeile and zeile not in arten:
                arten.append(zeile)
        return arten

    def save(self, commit=True):
        self.instance.arten = self.cleaned_data["arten_text"]
        return super().save(commit)
