from django import forms

from apps.core.auswahl import mit_vorhandenem
from apps.links.models import Link, LinkGruppe


def recht_auswahl(wert: str = "") -> list:
    from apps.konten import rechte

    auswahl = [("", "alle Angemeldeten")]
    for bereich, liste in rechte.bereiche():
        auswahl.append((bereich, [(r.code, r.bezeichnung) for r in liste]))
    bekannt = {c for _, gruppe in auswahl[1:] for c, _ in gruppe}
    if wert and wert not in bekannt:
        auswahl = mit_vorhandenem(auswahl, wert)
    return auswahl


class LinkForm(forms.ModelForm):
    recht = forms.ChoiceField(
        label="Sichtbar für",
        required=False,
        help_text="Leer = alle Angemeldeten; sonst nur, wer dieses Recht hat.",
    )

    class Meta:
        model = Link
        fields = ["titel", "untertitel", "beschreibung", "adresse", "symbol", "gruppe", "warnung",
                  "recht", "neuer_tab", "reihenfolge", "aktiv"]  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recht"].choices = recht_auswahl(self.instance.recht)
        self.fields["gruppe"].empty_label = "– ohne Gruppe –"


class GruppeForm(forms.ModelForm):
    class Meta:
        model = LinkGruppe
        fields = ["titel", "reihenfolge"]
