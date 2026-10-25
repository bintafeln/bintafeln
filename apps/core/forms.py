from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.template.defaultfilters import filesizeformat

from apps.core import geheimnis
from apps.core.auswahl import LAENDERCODE
from apps.core.farben import STANDARDFARBE
from apps.core.models import MailEinstellungen, SicherungsAuftrag, TafelEinstellungen

HINTERGRUND_MAX_BYTES = 5 * 1024 * 1024
LOGO_MAX_BYTES = 2 * 1024 * 1024


class BildEingabe(forms.ClearableFileInput):
    """Bild hochladen: aktuelles Bild als Vorschau, eindeutiges „Bild entfernen“."""

    template_name = "core/widgets/bild_eingabe.html"

    def __init__(self, attrs=None):
        super().__init__({"accept": "image/jpeg,image/png,image/webp", **(attrs or {})})


class StaatAuswahl(forms.Select):
    """Auswahl der Staatsangehörigkeit; jede Option trägt den Ländercode (data-land), damit der
    Browser den Namen in der Sprache der Besucher ergänzen kann."""

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        if value in LAENDERCODE:
            option["attrs"]["data-land"] = LAENDERCODE[value]
        return option


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
        fields = [
            "name",
            "logo",
            "farbe",
            "hintergrund_anmeldung",
            "hintergrund",
            "hintergrund_staerke",
            "strasse",
            "plz",
            "ort",
            "telefon",
            "email",
            "bundesland",
        ]
        widgets = {
            "logo": BildEingabe(),
            "hintergrund_anmeldung": BildEingabe(),
            "hintergrund": BildEingabe(),
            "farbe": forms.TextInput(attrs={"type": "color"}),
            "hintergrund_staerke": forms.NumberInput(
                attrs={
                    "type": "range",
                    "min": 0,
                    "max": 100,
                    "step": 5,
                    "oninput": "var h = document.getElementById(this.id + '_helptext'); "
                    "if (h) h.textContent = h.textContent.replace(/^Aktuell \\d+ %/, "
                    "'Aktuell ' + this.value + ' %')",
                }
            ),  # fmt: skip
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farbe"].required = False
        staerke = self.fields["hintergrund_staerke"]
        staerke.required = False
        staerke.help_text = f"Aktuell {self.instance.hintergrund_staerke} %. {staerke.help_text}"

    def clean_farbe(self):
        return self.cleaned_data.get("farbe") or STANDARDFARBE

    def clean_hintergrund_staerke(self):
        wert = self.cleaned_data.get("hintergrund_staerke")
        return self.instance.hintergrund_staerke if wert is None else wert

    def _bild(self, feld):
        bild = self.cleaned_data.get(feld)
        if bild and getattr(bild, "size", 0) > HINTERGRUND_MAX_BYTES:
            raise forms.ValidationError("Das Bild darf höchstens 5 MB groß sein.")
        return bild

    def clean_hintergrund_anmeldung(self):
        return self._bild("hintergrund_anmeldung")

    def clean_hintergrund(self):
        return self._bild("hintergrund")

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and getattr(logo, "size", 0) > LOGO_MAX_BYTES:
            raise forms.ValidationError("Das Logo darf höchstens 2 MB groß sein.")
        return logo


class MailEinstellungenForm(forms.ModelForm):
    passwort = forms.CharField(
        label="Passwort",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Leer lassen, um das gespeicherte Passwort zu behalten. Es wird verschlüsselt "
        "gespeichert und nie wieder angezeigt.",
    )
    passwort_loeschen = forms.BooleanField(label="Gespeichertes Passwort löschen", required=False)

    class Meta:
        model = MailEinstellungen
        fields = ["server", "port", "verschluesselung", "benutzer", "absender"]

    def clean_server(self):
        server = self.cleaned_data["server"].strip()
        if server.lower().startswith(("imap.", "pop.", "pop3.")):
            vorschlag = "smtp." + server.split(".", 1)[1]
            raise forms.ValidationError(
                f"„{server}“ ist ein Server zum Abholen von Mails. Zum Senden braucht es den "
                f"SMTP-Server, meist „{vorschlag}“."
            )
        return server

    def save(self, commit=True):
        instanz = super().save(commit=False)
        if self.cleaned_data.get("passwort_loeschen"):
            instanz.passwort_verschluesselt = ""
        elif self.cleaned_data.get("passwort"):
            instanz.passwort_verschluesselt = geheimnis.verschluesseln(
                self.cleaned_data["passwort"]
            )
        if commit:
            instanz.save()
        return instanz


class SicherungsAuftragForm(forms.ModelForm):
    """Sicherungsauftrag (ADR 0042). Ziele nur aus dem, was der Dienst unter /media, /mnt sieht."""

    ziel = forms.ChoiceField(label="Ziel", required=False)
    wochentage = forms.MultipleChoiceField(
        label="Wochentage", choices=SicherungsAuftrag.WOCHENTAGE,
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip

    class Meta:
        model = SicherungsAuftrag
        fields = ["name", "ziel", "aktiv", "wochentage", "uhrzeit", "anzahl", "tage"]
        widgets = {"uhrzeit": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}
        help_texts = {
            "anzahl": "Ältere Stände werden gelöscht. Leer = keine Grenze nach Anzahl.",
            "tage": "Ältere Stände werden gelöscht. Leer = keine Grenze nach Alter. "
            "Die neueste Sicherung bleibt immer erhalten.",
        }

    def __init__(self, *args, ziele=(), **kwargs):
        super().__init__(*args, **kwargs)
        auswahl = [("", "Sicherungsordner des Servers")]
        for pfad, frei, _gesamt in ziele:
            auswahl.append((pfad, f"{pfad} (frei: {filesizeformat(frei)})"))
        gespeichert = self.instance.ziel
        if gespeichert and gespeichert not in {p for p, _ in auswahl}:
            auswahl.append((gespeichert, f"{gespeichert} (zurzeit nicht angeschlossen)"))
        self.fields["ziel"].choices = auswahl
        self.fields["ziel"].help_text = (
            "Externe Platten und Netzlaufwerke erscheinen hier, sobald sie auf dem Server unter "
            "/media oder /mnt eingehängt sind. bintafeln legt dort einen Ordner „bintafeln“ an."
        )
        self.initial["wochentage"] = list(self.instance.wochentage)
        if self.instance.standard:
            del self.fields["ziel"]  # Der Standard-Auftrag sichert immer in den Sicherungsordner

    def clean_wochentage(self):
        return "".join(sorted(self.cleaned_data["wochentage"]))

    def clean_ziel(self):
        ziel = self.cleaned_data.get("ziel", "")
        if ziel and (not ziel.startswith(("/media/", "/mnt/")) or ".." in ziel.split("/")
                     or "|" in ziel or "\n" in ziel):  # fmt: skip
            raise forms.ValidationError("Nur Ordner unter /media oder /mnt sind möglich.")
        andere = SicherungsAuftrag.objects.exclude(pk=self.instance.pk).filter(ziel=ziel)
        if andere.exists():
            raise forms.ValidationError(
                f"In dieses Ziel sichert schon der Auftrag „{andere.first()}“. Je Ziel ein "
                "Auftrag, damit sich die Aufbewahrung nicht gegenseitig löscht."
            )
        return ziel

    def clean(self):
        daten = super().clean()
        if not daten.get("anzahl") and not daten.get("tage"):
            raise forms.ValidationError(
                "Bitte festlegen, wie lange Sicherungen aufbewahrt werden (Anzahl oder Tage), "
                "damit das Ziel nicht volläuft."
            )
        return daten
