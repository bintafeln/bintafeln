from django import forms
from django.contrib.auth import authenticate
from django_otp import match_token, user_has_device


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
        help_text="Nur nötig, wenn für Ihr Konto Zwei-Faktor eingerichtet ist.",
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
            code = (daten.get("otp_token") or "").strip()
            geraet = match_token(benutzer, code) if code else None
            if geraet is None:
                raise forms.ValidationError(self.fehler)
            self.geraet = geraet
        self.benutzer = benutzer
        return daten
