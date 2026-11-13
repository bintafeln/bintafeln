from django import forms

from apps.aufruf.models import TAGE, AufrufEinstellungen, AufrufInfo, HandyEinstellungen
from apps.core.forms import Mehrfachauswahl
from apps.kunden.models import Ausgabestelle, Zusatzfeld

INFO_MAX_BYTES = 10 * 1024 * 1024
BILDTYPEN = (".jpg", ".jpeg", ".png", ".webp")


class EinstellungenForm(forms.ModelForm):
    class Meta:
        model = AufrufEinstellungen
        fields = ["aktiv", "anzahl", "vorrang_feld", "vorrang_symbol", "eingelassene_ausblenden",
                  "spaetzuender_versatz", "zu_spaet_minuten", "beenden_nach_minuten",
                  "info_rotation", "wochentag_probe", "reihenfolge_mail"]  # fmt: skip

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


class HandyForm(forms.ModelForm):
    """Zentral für alle Ausgabestellen; bei „nur ausgewählte“ hier gleich die Ausgabestellen."""

    stellen = forms.ModelMultipleChoiceField(
        label="Ausgabestellen", required=False, queryset=Ausgabestelle.objects.none(),
        widget=Mehrfachauswahl(leer="keine"),
        help_text="Nur bei „nur an ausgewählten Ausgabestellen“; dort muss auch der Aufruf "
        "eingeschaltet sein.",
    )  # fmt: skip

    class Meta:
        model = HandyEinstellungen
        fields = ["modus", "stellen", "geraete", "push_vorher"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["push_vorher"].required = False
        self.fields["stellen"].queryset = Ausgabestelle.objects.filter(aktiv=True).order_by("name")
        self.initial["stellen"] = list(
            AufrufEinstellungen.objects.filter(handy=True).values_list("ausgabestelle", flat=True)
        )

    def clean_push_vorher(self):
        wert = self.cleaned_data.get("push_vorher")
        return self.instance.push_vorher if wert is None else wert

    def save(self, commit=True):
        e = super().save(commit)
        if self.instance.modus == HandyEinstellungen.Modus.AUSWAHL:
            gewaehlt = {s.pk for s in self.cleaned_data["stellen"]}
            for s in self.fields["stellen"].queryset:
                einst = AufrufEinstellungen.laden(s)
                if einst.handy != (s.pk in gewaehlt):
                    einst.handy = s.pk in gewaehlt
                    einst.save(update_fields=["handy"])
        return e


class NeueLinksForm(forms.Form):
    """Neue Links für Monitor, Anzeige und Kiosk: bewusst umständlich, weil danach jedes Gerät
    im Wartebereich neu eingerichtet werden muss."""

    verstanden = forms.BooleanField(
        label="Ich weiß: Monitor, Nummern-Anzeige, Kiosk und Abfrage dieser Ausgabestelle zeigen "
        "danach nichts mehr an, bis an jedem Gerät der neue Link geöffnet wurde.",
        error_messages={"required": "Bitte bestätigen, dass Sie die Folgen kennen."},
    )
    passwort = forms.CharField(
        label="Ihr Passwort", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text="Zur Sicherheit: das Passwort Ihres eigenen Kontos.",
    )  # fmt: skip

    def __init__(self, *args, benutzer, **kwargs):
        super().__init__(*args, **kwargs)
        self.benutzer = benutzer

    def clean_passwort(self):
        passwort = self.cleaned_data["passwort"]
        if not self.benutzer.check_password(passwort):
            raise forms.ValidationError("Das Passwort stimmt nicht.")
        return passwort
