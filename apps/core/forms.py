from django import forms
from django.contrib.auth import get_user_model, password_validation

from apps.core.models import TafelEinstellungen

LOGO_MAX_BYTES = 2 * 1024 * 1024


class EinrichtungForm(forms.Form):
    tafel_name = forms.CharField(label="Name der Tafel", max_length=200)
    username = forms.CharField(label="Benutzername", max_length=150)
    email = forms.EmailField(label="E-Mail", required=False)
    password1 = forms.CharField(label="Passwort", strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(
        label="Passwort wiederholen", strip=False, widget=forms.PasswordInput
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if get_user_model().objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return username

    def clean(self):
        daten = super().clean()
        pw1, pw2 = daten.get("password1"), daten.get("password2")
        if pw1 and pw2 and pw1 != pw2:
            self.add_error("password2", "Die Passwörter stimmen nicht überein.")
        elif pw1:
            probe = get_user_model()(username=daten.get("username", ""), email=daten.get("email"))
            try:
                password_validation.validate_password(pw1, probe)
            except forms.ValidationError as fehler:
                self.add_error("password1", fehler)
        return daten


class EinstellungenForm(forms.ModelForm):
    class Meta:
        model = TafelEinstellungen
        fields = ["name", "logo", "strasse", "plz", "ort", "telefon", "email"]

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and getattr(logo, "size", 0) > LOGO_MAX_BYTES:
            raise forms.ValidationError("Das Logo darf höchstens 2 MB groß sein.")
        return logo
