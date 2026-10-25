from django import forms
from django.contrib.auth import authenticate, get_user_model
from django_otp import match_token, user_has_device

from apps.core.auswahl import ANREDEN, FUEHRERSCHEINKLASSEN, mit_vorhandenem
from apps.konten import verwaltung
from apps.konten.models import (
    Dokument,
    DokumentKategorie,
    PersonalEinstellungen,
    Schulung,
    Stammdaten,
)
from apps.konten.zwei_faktor import code_bereinigen


class AnmeldeForm(forms.Form):
    """Anmeldung mit Benutzername und Passwort.

    Hat der Benutzer ein bestätigtes Zwei-Faktor-Gerät (TOTP), ist zusätzlich ein Code nötig.
    """

    username = forms.CharField(label="Benutzername", max_length=150)
    password = forms.CharField(label="Passwort", strip=False, widget=forms.PasswordInput)
    otp_token = forms.CharField(
        label="Zwei-Faktor-Code",
        required=False,
        max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
        help_text="Code aus der Authenticator-App oder ein Notfallcode. "
        "Nur nötig, wenn für Ihr Konto Zwei-Faktor eingerichtet ist.",
    )

    fehler = "Benutzername, Passwort oder Code ist falsch."

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.benutzer = None
        self.geraet = None
        super().__init__(*args, **kwargs)

    def clean(self):
        daten = super().clean()
        benutzername, passwort = daten.get("username"), daten.get("password")
        if not benutzername or not passwort:
            return daten
        benutzer = authenticate(self.request, username=benutzername, password=passwort)
        if benutzer is None:
            raise forms.ValidationError(self.fehler)
        if user_has_device(benutzer):
            code = code_bereinigen(daten.get("otp_token"))
            geraet = match_token(benutzer, code) if code else None
            if geraet is None:
                raise forms.ValidationError(self.fehler)
            self.geraet = geraet
        self.benutzer = benutzer
        return daten


class CodeForm(forms.Form):
    code = forms.CharField(
        label="Code",
        max_length=20,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric", "autofocus": True}
        ),
    )


class MitarbeiterForm(forms.ModelForm):
    """Konto anlegen oder bearbeiten. Rollen kommen als Häkchen dazu."""

    rollen = forms.MultipleChoiceField(
        label="Rollen", required=False, widget=forms.CheckboxSelectMultiple
    )
    zugang = forms.ChoiceField(
        label="Zugang",
        choices=[
            ("startpasswort", "Startpasswort anzeigen und persönlich weitergeben"),
            ("einladung", "Einladung per Mail mit Link zum Passwort-Festlegen"),
        ],
        initial="startpasswort",
        widget=forms.RadioSelect,
    )

    class Meta:
        model = get_user_model()
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "beschaeftigung",
            "ausgabestellen",
        ]
        help_texts = {"username": "Zum Anmelden. Buchstaben, Ziffern und @ . + - _"}
        widgets = {"ausgabestellen": forms.CheckboxSelectMultiple}

    def __init__(self, *args, verwalter, mail_moeglich=False, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk or not mail_moeglich:
            del self.fields["zugang"]
        self.fields["rollen"].choices = [(r, r) for r in verwaltung.vergebbare_rollen(verwalter)]
        if self.instance.pk:
            self.fields["rollen"].initial = list(
                self.instance.groups.values_list("name", flat=True)
            )

    def clean(self):
        daten = super().clean()
        if daten.get("zugang") == "einladung" and not daten.get("email"):
            self.add_error(
                "email", "Für eine Einladung per Mail bitte eine E-Mail-Adresse angeben."
            )
        return daten

    def clean_username(self):
        name = self.cleaned_data["username"]
        andere = get_user_model().objects.filter(username__iexact=name)
        if andere.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return name


class DatumEingabe(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class StammdatenForm(forms.ModelForm):
    """Feste Werte und registrierte Mitarbeitende immer als Auswahl, nie als Freitext."""

    anrede = forms.ChoiceField(label="Anrede", required=False)
    fs_klassen = forms.MultipleChoiceField(
        label="Führerscheinklassen",
        required=False,
        choices=[(k, k) for k in FUEHRERSCHEINKLASSEN],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "klassen"}),
    )
    fs_gesehen_von = forms.ChoiceField(label="Gesehen von", required=False)

    class Meta:
        model = Stammdaten
        fields = [
            "anrede", "geburtsdatum", "strasse", "plz", "ort", "telefon", "handy",
            "notfall_name", "notfall_telefon", "eintritt", "austritt", "bemerkung",
            "fs_klassen", "fs_gueltig_bis", "fs_gesehen_am", "fs_gesehen_von",
            "ifsg_erstbelehrung_am", "ifsg_belehrung_am",
        ]  # fmt: skip
        widgets = {
            "geburtsdatum": DatumEingabe(),
            "eintritt": DatumEingabe(),
            "austritt": DatumEingabe(),
            "fs_gueltig_bis": DatumEingabe(),
            "fs_gesehen_am": DatumEingabe(),
            "ifsg_erstbelehrung_am": DatumEingabe(),
            "ifsg_belehrung_am": DatumEingabe(),
            "bemerkung": forms.Textarea(attrs={"rows": 3}),
        }

    # Abschnitte für die Anzeige (Feldnamen in Reihenfolge).
    ABSCHNITTE = [
        ("Person", ["anrede", "geburtsdatum", "eintritt", "austritt"]),
        ("Kontakt", ["strasse", "plz", "ort", "telefon", "handy"]),
        ("Notfallkontakt", ["notfall_name", "notfall_telefon"]),
        ("Führerschein", ["fs_klassen", "fs_gueltig_bis", "fs_gesehen_am", "fs_gesehen_von"]),
        ("Belehrung nach Infektionsschutzgesetz", ["ifsg_erstbelehrung_am", "ifsg_belehrung_am"]),
        ("Sonstiges", ["bemerkung"]),
    ]

    def __init__(self, *args, angemeldet=None, **kwargs):
        super().__init__(*args, **kwargs)
        s = self.instance
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, s.anrede)
        vorhanden = [k.strip() for k in s.fs_klassen.split(",") if k.strip()]
        self.initial["fs_klassen"] = vorhanden
        # Gespeicherte Klassen, die nicht (mehr) in der Liste stehen, bleiben wählbar.
        self.fields["fs_klassen"].choices = [(k, k) for k in FUEHRERSCHEINKLASSEN] + [
            (k, k) for k in vorhanden if k not in FUEHRERSCHEINKLASSEN
        ]
        namen = [str(b) for b in get_user_model().objects.filter(is_active=True).order_by(
            "last_name", "first_name", "username")]  # fmt: skip
        self.fields["fs_gesehen_von"].choices = mit_vorhandenem(
            [("", "—")] + [(n, n) for n in namen], s.fs_gesehen_von
        )
        if not s.fs_gesehen_von and angemeldet is not None:
            self.initial["fs_gesehen_von"] = str(angemeldet)  # vorbelegt: wer gerade einträgt

    def clean_fs_klassen(self):
        return ", ".join(self.cleaned_data["fs_klassen"])

    def clean(self):
        daten = super().clean()
        if not daten.get("fs_gesehen_am"):
            daten["fs_gesehen_von"] = ""  # die Vorbelegung zählt nur mit Datum
        return daten

    def abschnitte(self):
        return [(titel, [self[f] for f in felder]) for titel, felder in self.ABSCHNITTE]


class SchulungForm(forms.ModelForm):
    class Meta:
        model = Schulung
        fields = ["thema", "datum", "gueltig_bis", "bemerkung"]
        widgets = {"datum": DatumEingabe(), "gueltig_bis": DatumEingabe()}


class PersonalEinstellungenForm(forms.ModelForm):
    class Meta:
        model = PersonalEinstellungen
        fields = [
            "fs_pruefung_monate",
            "ifsg_wiederholung_monate",
            "vorlauf_tage",
            "fs_kopie_erlaubt",
            "urlaub_verfall_monat",
            "urlaub_verfall_tag",
            "stammdaten_loeschen_jahre",
        ]


class DokumentForm(forms.ModelForm):
    datei = forms.FileField(label="Datei (PDF oder Foto, höchstens 10 MB)")

    class Meta:
        model = Dokument
        fields = ["kategorie", "titel", "datum"]
        widgets = {"datum": DatumEingabe()}

    def __init__(self, *args, kategorien, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kategorie"].queryset = kategorien


class DokumentKategorieForm(forms.ModelForm):
    class Meta:
        model = DokumentKategorie
        fields = ["name", "nur_personal"]
