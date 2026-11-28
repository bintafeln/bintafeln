import json

from django import forms
from django.urls import reverse
from django.utils import timezone

from apps.core.auswahl import MITGLIEDSARTEN
from apps.core.forms import Mehrfachauswahl
from apps.konten import rollen
from apps.serienbriefe import empfaenger, frei, gestaltung
from apps.serienbriefe.empfaenger import karten
from apps.serienbriefe.models import Versand, Vorlage


class VorlageForm(forms.ModelForm):
    """Text und Fußzeile im Editor (static/js/html_editor.js), gespeichert als bereinigtes HTML."""

    # Liste als JSON-Text; static/js/brief_frei.js pflegt sie (Ziehen in der Vorschau, Maße)
    freie_grafiken = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Vorlage
        fields = ["name", "betreff", "text", "briefkopf", "fusszeile", "freie_grafiken",
                  "verwendung"]  # fmt: skip
        widgets = {
            "betreff": forms.TextInput(attrs={"data-platzhalter-ziel": ""}),
            "text": forms.Textarea(attrs={"rows": 16, "class": "html-eingabe",
                                          "data-editor": "", "data-editor-ohne": "link bild"}),
            "fusszeile": forms.Textarea(attrs={"rows": 3, "class": "html-eingabe",
                                               "data-editor": "", "data-editor-ohne": "link bild"}),
        }  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        namen = {k: name for k, name, _ in karten()}
        self.fields["text"].widget.attrs["data-platzhalter"] = json.dumps(namen)
        # Knopf „Grafik“ im Editor (ADR 0138): Liste und Hochladen über diese Adresse
        self.fields["text"].widget.attrs["data-editor-grafiken"] = reverse("serienbriefe:grafiken")
        if not self.is_bound:
            self.initial["freie_grafiken"] = json.dumps(frei.lesen(self.instance.freie_grafiken))
        for feld in ("text", "fusszeile"):  # ältere Vorlagen aus reinem Text als Absätze
            if self.instance.pk and not self.is_bound:
                self.initial[feld] = gestaltung.als_html(getattr(self.instance, feld))

    def clean_text(self):
        text = gestaltung.speichern(self.cleaned_data["text"])
        if not gestaltung.mail_text(text).strip():
            raise forms.ValidationError("Bitte einen Text schreiben.")
        return text

    def clean_freie_grafiken(self):
        return frei.lesen(self.cleaned_data["freie_grafiken"])

    def clean_fusszeile(self):
        fuss = gestaltung.speichern(self.cleaned_data["fusszeile"])
        return fuss if gestaltung.mail_text(fuss).strip() else ""


class AuswahlForm(forms.Form):
    vorlage = forms.ModelChoiceField(label="Vorlage", queryset=Vorlage.objects.all())
    quelle = forms.MultipleChoiceField(
        label="Empfänger", widget=Mehrfachauswahl(leer="– bitte anhaken –"),
        help_text="Mehrere Haken ergeben eine gemeinsame Liste; jeder bekommt den Brief nur "
        "einmal.",
        error_messages={"required": "Bitte mindestens eine Gruppe oder Kategorie anhaken."},
    )  # fmt: skip
    versandart = forms.ChoiceField(label="Versand", choices=Versand.Art.choices,
                                   widget=forms.RadioSelect, initial=Versand.Art.BRIEF)  # fmt: skip
    jahr = forms.TypedChoiceField(
        label="Jahr", coerce=int,
        help_text="Für Spender, offene Beiträge und die Platzhalter {spendensumme}, {jahr}.",
    )  # fmt: skip
    nur_einwilligung = forms.BooleanField(
        label="Nur mit Einwilligung (Post bzw. E-Mail)", required=False,
        help_text="Gilt für Adresskategorien, Spender und die zusammengestellte Liste.",
    )  # fmt: skip
    mindestbetrag = forms.DecimalField(label="Mindestsumme im Jahr (Euro)",
                                       required=False, localize=True)  # fmt: skip
    mitgliedsarten = forms.MultipleChoiceField(
        label="Mitgliedsarten", required=False, widget=Mehrfachauswahl(leer="alle Arten"),
        choices=[(a, a) for a in MITGLIEDSARTEN],
    )  # fmt: skip
    nur_offen = forms.BooleanField(label="Nur mit offenem Beitrag im Jahr",
                                   required=False)  # fmt: skip
    kundengruppen = forms.ModelMultipleChoiceField(
        label="Kundengruppen", required=False,
        widget=Mehrfachauswahl(leer="alle Kundengruppen"), queryset=None,
    )  # fmt: skip

    def __init__(self, *args, benutzer=None, liste=0, **kwargs):
        """``liste``: Zahl der Adressen einer aus dem Adressbuch mitgebrachten Liste (0 = keine)."""
        super().__init__(*args, **kwargs)
        from apps.kunden.models import Kundengruppe

        quellen = empfaenger.wahl(rollen.hat_recht(benutzer, "serienbriefe.kunden"), liste)
        self.fields["quelle"].choices = quellen
        heute = timezone.localdate().year
        self.fields["jahr"].choices = [(j, j) for j in range(heute, heute - 6, -1)]
        if "kunden" in dict(quellen):
            self.fields["kundengruppen"].queryset = Kundengruppe.objects.all()
        else:
            del self.fields["kundengruppen"]
        from apps.mitglieder.models import MitgliederEinstellungen

        if not MitgliederEinstellungen.mit_beitraegen():
            del self.fields["nur_offen"]
            self.fields[
                "jahr"
            ].help_text = "Für Spender und die Platzhalter {spendensumme}, {jahr}."
