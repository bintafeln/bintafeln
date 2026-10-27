from django import forms

from apps.aufruf.models import TAGE, AufrufEinstellungen, AufrufInfo
from apps.kunden.models import Ausgabestelle, Zusatzfeld

INFO_MAX_BYTES = 10 * 1024 * 1024
BILDTYPEN = (".jpg", ".jpeg", ".png", ".webp")


class EinstellungenForm(forms.ModelForm):
    class Meta:
        model = AufrufEinstellungen
        fields = ["aktiv", "anzahl", "vorrang_feld", "vorrang_symbol", "eingelassene_ausblenden",
                  "automatisch_weiter", "spaetzuender_versatz", "zu_spaet_minuten", "info_rotation",
                  "wochentag_probe"]  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        feld = self.fields["vorrang_feld"]
        feld.queryset = Zusatzfeld.objects.filter(typ=Zusatzfeld.Typ.JA_NEIN, aktiv=True)
        feld.empty_label = "– kein Vorrang –"
        self.fields["wochentag_probe"].choices = [("", "– aus (heutiger Wochentag) –"),
                                                  *TAGE]  # fmt: skip


class InfoForm(forms.ModelForm):
    adresse = forms.URLField(
        label="Adresse der Webseite", required=False, assume_scheme="https",
        help_text=AufrufInfo._meta.get_field("adresse").help_text,
    )  # fmt: skip

    class Meta:
        model = AufrufInfo
        fields = ["titel", "art", "text", "datei", "adresse", "dauer", "ausgabestellen",
                  "reihenfolge", "aktiv"]  # fmt: skip
        widgets = {"ausgabestellen": forms.CheckboxSelectMultiple,
                   "text": forms.Textarea(attrs={"rows": 6})}  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ausgabestellen"].queryset = Ausgabestelle.objects.filter(aktiv=True)

    def clean(self):
        daten = super().clean()
        art = daten.get("art")
        datei = daten.get("datei")
        if datei and getattr(datei, "size", 0) > INFO_MAX_BYTES:
            self.add_error("datei", "Die Datei darf höchstens 10 MB groß sein.")
        name = (getattr(datei, "name", "") or "").lower()
        if art == AufrufInfo.Art.TEXT and not daten.get("text", "").strip():
            self.add_error("text", "Bitte einen Text eingeben.")
        elif art == AufrufInfo.Art.WEBSEITE and not daten.get("adresse"):
            self.add_error("adresse", "Bitte die Adresse der Webseite angeben.")
        elif art == AufrufInfo.Art.BILD:
            if not datei:
                self.add_error("datei", "Bitte ein Bild hochladen.")
            elif not name.endswith(BILDTYPEN):
                self.add_error("datei", "Bitte ein Bild als JPG, PNG oder WebP.")
        elif art == AufrufInfo.Art.PDF:
            if not datei:
                self.add_error("datei", "Bitte ein PDF hochladen.")
            elif not name.endswith(".pdf"):
                self.add_error("datei", "Bitte eine PDF-Datei.")
        return daten
