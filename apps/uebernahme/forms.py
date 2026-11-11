from django import forms

from apps.uebernahme.models import _nummer_text_lesen, _nummer_text_schreiben


class EinstellungenForm(forms.Form):
    """Zuordnungen als Textfeld „Nummer = Text“ (eine je Zeile)."""

    ausgabestellen = forms.CharField(
        label="Ausgabestellen (Nummer → Name)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Nur nötig, wenn der Export die Ausgabestellen nicht selbst enthält. "
        "Eine Zuordnung je Zeile, z. B. „1 = Innenstadt“.",
    )
    einkommensarten = forms.CharField(
        label="Einkommensarten (Nummer → Text)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="Die Nummern stehen in der Konfiguration des bisherigen Programms. Eine "
        "Zuordnung je Zeile, z. B. „6 = Rente“. Ohne Eintrag bleibt die Einkommensart beim "
        "Import leer.",
    )

    @classmethod
    def aus_einstellungen(cls, einstellungen):
        return cls(
            initial={
                "ausgabestellen": _nummer_text_schreiben(einstellungen.ausgabestellen),
                "einkommensarten": _nummer_text_schreiben(einstellungen.einkommensarten),
            }
        )

    def clean_ausgabestellen(self):
        return _nummer_text_lesen(self.cleaned_data["ausgabestellen"])

    def clean_einkommensarten(self):
        return _nummer_text_lesen(self.cleaned_data["einkommensarten"])
