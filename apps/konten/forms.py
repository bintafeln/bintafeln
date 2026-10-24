from django import forms
from django.contrib.auth import authenticate, get_user_model
from django_otp import match_token, user_has_device

from apps.konten import rollen, verwaltung
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

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email", "beschaeftigung"]
        help_texts = {"username": "Zum Anmelden. Buchstaben, Ziffern und @ . + - _"}

    def __init__(self, *args, verwalter, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rollen"].choices = [(r, r) for r in verwaltung.vergebbare_rollen(verwalter)]
        if self.instance.pk:
            self.fields["rollen"].initial = list(
                self.instance.groups.filter(name__in=rollen.ALLE).values_list("name", flat=True)
            )

    def clean_username(self):
        name = self.cleaned_data["username"]
        andere = get_user_model().objects.filter(username__iexact=name)
        if andere.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return name
