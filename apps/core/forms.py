from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.db.models import Max
from django.template.defaultfilters import filesizeformat

from apps.core import bilder, geheimnis
from apps.core.auswahl import LAENDERCODE
from apps.core.farben import STANDARDFARBE
from apps.core.models import (
    Fernsicherung,
    Hintergrundbild,
    MailEinstellungen,
    SicherungsAuftrag,
    TafelEinstellungen,
)
from apps.core.module import auswahl as modul_auswahl

HINTERGRUND_MAX_BYTES = 5 * 1024 * 1024
LOGO_MAX_BYTES = 2 * 1024 * 1024


def _verkleinert(bild, kante, transparenz=False):
    """Neu hochgeladene Bilder verkleinern; gespeicherte (oder „entfernen“) bleiben."""
    if not bild or not hasattr(bild, "content_type"):
        return bild
    return bilder.verkleinern(bild, kante, transparenz=transparenz) or bild


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


class Mehrfachauswahl(forms.CheckboxSelectMultiple):
    """Mehrfachauswahl als aufklappbares Menü mit Häkchen: zu sieht man, was gewählt ist (leer =
    ``leer``); lange Listen bekommen ein Suchfeld. Verhalten in static/js/mehrfachauswahl.js,
    ohne JavaScript klappt es trotzdem auf und zu."""

    template_name = "core/widgets/mehrfachauswahl.html"

    def __init__(self, attrs=None, choices=(), leer="alle", suche_ab=8):
        super().__init__(attrs, choices)
        self.leer, self.suche_ab = leer, suche_ab

    def get_context(self, name, value, attrs):
        kontext = super().get_context(name, value, attrs)
        optionen = [o for _, gruppe, _ in kontext["widget"]["optgroups"] for o in gruppe]
        kontext["widget"].update(
            leer=self.leer, suche=len(optionen) >= self.suche_ab,
            gewaehlt=[str(o["label"]) for o in optionen if o["selected"]],
        )  # fmt: skip
        return kontext


class MehrereBilder(forms.FileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        super().__init__({"accept": "image/jpeg,image/png,image/webp", "multiple": True,
                          **(attrs or {})})  # fmt: skip


class MehrereBilderFeld(forms.ImageField):
    """Mehrere Bilder auf einmal hochladen; ergibt eine Liste (leer = keins)."""

    def __init__(self, **kwargs):
        super().__init__(widget=MehrereBilder(), required=False, **kwargs)

    def clean(self, data, initial=None):
        dateien = data if isinstance(data, (list, tuple)) else [data]
        return [super(MehrereBilderFeld, self).clean(d, initial) for d in dateien if d]


class EinstellungenForm(forms.ModelForm):
    weitere_anmeldung = MehrereBilderFeld(
        label="Weitere Bilder der Anmeldeseite",
        help_text="Mehrere auf einmal wählbar. Sie wechseln mit dem Bild oben ab.",
    )
    weitere_seiten = MehrereBilderFeld(
        label="Weitere Bilder der übrigen Seiten",
        help_text="Mehrere auf einmal wählbar. Sie wechseln mit dem Bild oben ab.",
    )
    module = forms.MultipleChoiceField(
        label="Zusätzliche Module", required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Ausgeschaltete Module erscheinen nirgends: kein Menü, keine Seiten, keine "
        "Rechte, keine Hilfe. Ihre Daten bleiben erhalten, bis man sie wieder einschaltet.",
    )  # fmt: skip

    class Meta:
        model = TafelEinstellungen
        fields = [
            "name",
            "logo",
            "app_symbol",
            "farbe",
            "hintergrund_anmeldung",
            "weitere_anmeldung",
            "hintergrund",
            "weitere_seiten",
            "hintergrund_staerke",
            "hintergrund_wechsel",
            "strasse",
            "plz",
            "ort",
            "telefon",
            "email",
            "bundesland",
            "papierkorb_tage",
            "module",
        ]
        widgets = {
            "logo": BildEingabe(),
            "app_symbol": BildEingabe(),
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
        self.fields["module"].choices = modul_auswahl()
        self.fields["farbe"].required = False
        self.fields["papierkorb_tage"].required = False  # fehlt, bleibt die bisherige Zahl
        staerke = self.fields["hintergrund_staerke"]
        staerke.required = False
        self.fields["hintergrund_wechsel"].required = False
        staerke.help_text = f"Aktuell {self.instance.hintergrund_staerke} %. {staerke.help_text}"

    def clean_farbe(self):
        return self.cleaned_data.get("farbe") or STANDARDFARBE

    def clean_papierkorb_tage(self):
        return self.cleaned_data.get("papierkorb_tage") or self.instance.papierkorb_tage

    def clean_hintergrund_staerke(self):
        wert = self.cleaned_data.get("hintergrund_staerke")
        return self.instance.hintergrund_staerke if wert is None else wert

    def _bild(self, feld):
        bild = self.cleaned_data.get(feld)
        if bild and getattr(bild, "size", 0) > HINTERGRUND_MAX_BYTES:
            raise forms.ValidationError("Das Bild darf höchstens 5 MB groß sein.")
        return _verkleinert(bild, bilder.HINTERGRUND_KANTE)

    def _weitere(self, feld):
        ergebnis = []
        for bild in self.cleaned_data.get(feld) or []:
            if getattr(bild, "size", 0) > HINTERGRUND_MAX_BYTES:
                raise forms.ValidationError(f"„{bild.name}“ ist größer als 5 MB.")
            ergebnis.append(_verkleinert(bild, bilder.HINTERGRUND_KANTE))
        return ergebnis

    def clean_weitere_anmeldung(self):
        return self._weitere("weitere_anmeldung")

    def clean_weitere_seiten(self):
        return self._weitere("weitere_seiten")

    def clean_hintergrund_wechsel(self):
        wert = self.cleaned_data.get("hintergrund_wechsel")
        return self.instance.hintergrund_wechsel if wert is None else wert

    def save(self, commit=True):
        instanz = super().save(commit)
        B = Hintergrundbild.Bereich
        for feld, bereich in (("weitere_anmeldung", B.ANMELDUNG), ("weitere_seiten", B.SEITEN)):
            letzte = Hintergrundbild.objects.filter(bereich=bereich).aggregate(m=Max("reihenfolge"))
            start = (letzte["m"] or 0) + 1
            for nr, bild in enumerate(self.cleaned_data.get(feld) or [], start=start):
                Hintergrundbild.objects.create(bereich=bereich, bild=bild, reihenfolge=nr)
        return instanz

    def clean_hintergrund_anmeldung(self):
        return self._bild("hintergrund_anmeldung")

    def clean_hintergrund(self):
        return self._bild("hintergrund")

    def clean_app_symbol(self):
        symbol = self.cleaned_data.get("app_symbol")
        if not symbol or not hasattr(symbol, "content_type"):
            return symbol  # unverändert oder gelöscht
        if getattr(symbol, "size", 0) > LOGO_MAX_BYTES:
            raise forms.ValidationError("Das App-Symbol darf höchstens 2 MB groß sein.")
        quadrat = bilder.app_symbol(symbol)
        if quadrat is None:
            raise forms.ValidationError("Das Bild lässt sich nicht lesen.")
        return quadrat

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and getattr(logo, "size", 0) > LOGO_MAX_BYTES:
            raise forms.ValidationError("Das Logo darf höchstens 2 MB groß sein.")
        return _verkleinert(logo, bilder.LOGO_KANTE, transparenz=True)


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
        # Fernablagen (rclone, ADR 0106) als Ziel anbieten, wenn eingerichtet
        self.remotes = Fernsicherung.laden().remotes()
        for name in self.remotes:
            auswahl.append((f"{name}:bintafeln", f"Fernablage außer Haus „{name}“"))
        gespeichert = self.instance.ziel
        if gespeichert and gespeichert not in {p for p, _ in auswahl}:
            hinweis = "Fernablage fehlt" if ":" in gespeichert else "zurzeit nicht angeschlossen"
            auswahl.append((gespeichert, f"{gespeichert} ({hinweis})"))
        self.fields["ziel"].choices = auswahl
        self.fields["ziel"].help_text = (
            "Externe Platten und Netzlaufwerke erscheinen hier, sobald sie auf dem Server unter "
            "/media oder /mnt eingehängt sind. bintafeln legt dort einen Ordner „bintafeln“ an. "
            "Fernablagen außer Haus richtet man unten auf der Sicherungsseite ein."
        )
        self.initial["wochentage"] = list(self.instance.wochentage)
        if self.instance.standard:
            del self.fields["ziel"]  # Der Standard-Auftrag sichert immer in den Sicherungsordner

    def clean_wochentage(self):
        return "".join(sorted(self.cleaned_data["wochentage"]))

    def clean_ziel(self):
        ziel = self.cleaned_data.get("ziel", "")
        fern = ziel.split(":", 1)[0] in getattr(self, "remotes", []) if ":" in ziel else False
        lokal = ziel.startswith(("/media/", "/mnt/")) and ".." not in ziel.split("/")
        if ziel and (not (fern or lokal) or "|" in ziel or "\n" in ziel):
            raise forms.ValidationError(
                "Nur ein Ordner unter /media oder /mnt oder eine eingerichtete Fernablage."
            )
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


class FernsicherungForm(forms.Form):
    """Geführte Eingabe für eine Fernablage (rclone, ADR 0106): Art wählen, Felder ausfüllen –
    bintafeln baut daraus den rclone-Block und verschleiert Passwörter. Passwörter/Schlüssel
    werden aus Sicherheitsgründen nie wieder angezeigt: leer lassen = unverändert."""

    GEHEIM = forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"})
    ART = [
        ("", "– bitte wählen –"),
        ("sftp", "SFTP (SSH-Server / Storage Box)"),
        ("webdav", "Nextcloud / ownCloud / WebDAV"),
        ("s3", "S3-kompatibel (Backblaze B2, Wasabi, Hetzner …)"),
        ("ftp", "FTP / FTPS"),
        ("block", "Experten: rclone-Block selbst einfügen"),
    ]
    art = forms.ChoiceField(label="Art der Fernablage", choices=ART, required=False)

    # SFTP
    sftp_host = forms.CharField(label="Server (Host)", required=False,
                                help_text="z. B. u123456.your-storagebox.de")  # fmt: skip
    sftp_port = forms.IntegerField(label="Port", required=False, min_value=1, max_value=65535,
                                   help_text="Standard 22.")  # fmt: skip
    sftp_user = forms.CharField(label="Benutzername", required=False)
    sftp_pass = forms.CharField(label="Passwort", required=False, widget=GEHEIM,
        help_text="Leer lassen = unverändert. Oder stattdessen unten eine Schlüsseldatei "
        "hochladen.")  # fmt: skip
    sftp_key = forms.FileField(label="Private Schlüsseldatei (statt Passwort)", required=False,
        help_text="OpenSSH-Privatschlüssel OHNE Passphrase (z. B. id_ed25519). Den passenden "
        "öffentlichen Schlüssel beim Server hinterlegen.")  # fmt: skip
    sftp_key_entfernen = forms.BooleanField(label="Gespeicherte Schlüsseldatei entfernen",
                                            required=False)  # fmt: skip

    # Nextcloud / ownCloud / WebDAV
    dav_vendor = forms.ChoiceField(
        label="Anbieter",
        required=False,
        choices=[
            ("nextcloud", "Nextcloud"),
            ("owncloud", "ownCloud"),
            ("other", "anderer WebDAV-Server"),
        ],
    )
    dav_url = forms.CharField(label="WebDAV-Adresse", required=False,
        help_text="Nextcloud/ownCloud: https://cloud.example.org/remote.php/dav/files/BENUTZER/")  # fmt: skip  # noqa: E501
    dav_user = forms.CharField(label="Benutzername", required=False)
    dav_pass = forms.CharField(label="Passwort", required=False, widget=GEHEIM,
        help_text="Bei Nextcloud/ownCloud am besten ein App-Passwort (Einstellungen → Sicherheit → "
        "App-Passwort). Leer lassen = unverändert.")  # fmt: skip

    # S3-kompatibel
    s3_provider = forms.ChoiceField(label="Anbieter", required=False, choices=[
        ("Other", "anderer / S3-kompatibel"), ("AWS", "Amazon AWS"), ("Wasabi", "Wasabi"),
        ("Backblaze", "Backblaze B2")])  # fmt: skip
    s3_key = forms.CharField(label="Access Key ID", required=False)
    s3_secret = forms.CharField(label="Secret Access Key", required=False, widget=GEHEIM,
                                help_text="Leer lassen = unverändert.")  # fmt: skip
    s3_endpoint = forms.CharField(label="Endpunkt (Endpoint)", required=False,
        help_text="z. B. s3.eu-central-003.backblazeb2.com; bei Amazon AWS leer.")  # fmt: skip
    s3_region = forms.CharField(label="Region", required=False, help_text="falls nötig, sonst leer")

    # FTP / FTPS
    ftp_host = forms.CharField(label="Server (Host)", required=False)
    ftp_port = forms.IntegerField(label="Port", required=False, min_value=1, max_value=65535,
                                  help_text="Standard 21.")  # fmt: skip
    ftp_user = forms.CharField(label="Benutzername", required=False)
    ftp_pass = forms.CharField(label="Passwort", required=False, widget=GEHEIM,
                               help_text="Leer lassen = unverändert.")  # fmt: skip
    ftp_tls = forms.BooleanField(label="Verschlüsselt (FTPS, explizit)", required=False)

    # Experten
    konfig = forms.CharField(
        label="rclone-Remote-Block", required=False,
        widget=forms.Textarea(attrs={"rows": 7, "spellcheck": "false", "autocomplete": "off",
                                     "placeholder": "[fern]\ntype = sftp\nhost = …\nuser = …\n…"}),
        help_text="Nur für Sonderfälle (z. B. Google Drive): einen fertigen rclone-Block einfügen. "
        "Der Name in eckigen Klammern muss „fern“ sein.",
    )  # fmt: skip
    entfernen = forms.BooleanField(label="Gespeicherte Fernablage entfernen", required=False)

    NAME = "fern"  # fester Remote-Name

    def __init__(self, *args, instanz=None, **kwargs):
        from apps.core.models import Fernsicherung

        self.instanz = instanz or Fernsicherung.laden()
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self._vorbelegen()

    def _vorbelegen(self):
        """Die nicht-geheimen Werte der gespeicherten Konfig in die Felder übernehmen."""
        from apps.core import rclone

        alt = rclone.block_parsen(self.instanz.konfig)
        typ = alt.get("type")
        if typ == "sftp":
            self.initial.update(art="sftp", sftp_host=alt.get("host"), sftp_port=alt.get("port"),
                                sftp_user=alt.get("user"))  # fmt: skip
        elif typ == "webdav":
            self.initial.update(art="webdav", dav_vendor=alt.get("vendor", "nextcloud"),
                                dav_url=alt.get("url"), dav_user=alt.get("user"))  # fmt: skip
        elif typ == "s3":
            self.initial.update(art="s3", s3_provider=alt.get("provider", "Other"),
                                s3_key=alt.get("access_key_id"), s3_endpoint=alt.get("endpoint"),
                                s3_region=alt.get("region"))  # fmt: skip
        elif typ == "ftp":
            self.initial.update(art="ftp", ftp_host=alt.get("host"), ftp_port=alt.get("port"),
                                ftp_user=alt.get("user"),
                                ftp_tls=alt.get("explicit_tls") == "true")  # fmt: skip
        elif typ:
            self.initial.update(art="block", konfig=self.instanz.konfig)

    def _geheim(self, feld, alt_schluessel, alt, art_passt, verschleiern=True):
        """Neues Geheimnis verschleiern, sonst das gespeicherte übernehmen (bei gleicher Art)."""
        from apps.core import rclone

        wert = self.cleaned_data.get(feld, "")
        if wert:
            return rclone.obscure(wert) if verschleiern else wert
        return alt.get(alt_schluessel, "") if art_passt else ""

    def clean(self):
        d = super().clean()
        art = d.get("art")
        if art in ("", "block") or d.get("entfernen"):
            return d
        pflicht = {"sftp": ("sftp_host", "sftp_user"), "webdav": ("dav_url", "dav_user"),
                   "s3": ("s3_key",), "ftp": ("ftp_host", "ftp_user")}  # fmt: skip
        for feld in pflicht.get(art, ()):
            if not d.get(feld):
                self.add_error(feld, "Bitte ausfüllen.")
        return d

    def speichern(self) -> None:
        from apps.core import rclone
        from apps.core.models import Fernsicherung

        obj: Fernsicherung = self.instanz
        d = self.cleaned_data
        art = d.get("art")
        if d.get("entfernen"):
            obj.konfig_setzen("")
            obj.schluessel_setzen("")
            obj.save()
            return
        if not art:
            return  # nichts gewählt, nicht entfernt: unverändert
        if art == "block":
            if d.get("konfig", "").strip():
                obj.konfig_setzen(d["konfig"])
                obj.save()
            return
        alt = rclone.block_parsen(obj.konfig)
        passt = alt.get("type") == art  # gleiche Art wie gespeichert → Geheimnis wiederverwendbar
        werte = {}
        if art == "sftp":
            schluessel = self._sftp_schluessel(obj, passt)
            werte = {"host": d["sftp_host"], "port": d.get("sftp_port"), "user": d["sftp_user"]}
            if schluessel:
                werte["key_file"] = rclone.SCHLUESSELDATEI_PFAD
            else:
                werte["pass"] = self._geheim("sftp_pass", "pass", alt, passt)
        elif art == "webdav":
            werte = {"url": d["dav_url"], "user": d["dav_user"],
                     "vendor": d.get("dav_vendor") or "nextcloud",
                     "pass": self._geheim("dav_pass", "pass", alt, passt)}  # fmt: skip
        elif art == "s3":
            werte = {"provider": d.get("s3_provider"), "access_key_id": d["s3_key"],
                     "secret_access_key": self._geheim("s3_secret", "secret_access_key", alt,
                                                        passt, verschleiern=False),
                     "endpoint": d.get("s3_endpoint"), "region": d.get("s3_region")}  # fmt: skip
        elif art == "ftp":
            werte = {"host": d["ftp_host"], "port": d.get("ftp_port"), "user": d["ftp_user"],
                     "pass": self._geheim("ftp_pass", "pass", alt, passt),
                     "tls": d.get("ftp_tls")}  # fmt: skip
        obj.konfig_setzen(rclone.block_bauen(self.NAME, art, werte))
        obj.save()

    def _sftp_schluessel(self, obj, passt) -> str:
        """Neue Schlüsseldatei speichern / entfernen / behalten; liefert den aktuellen Schlüssel."""
        if self.cleaned_data.get("sftp_key_entfernen"):
            obj.schluessel_setzen("")
            return ""
        datei = self.cleaned_data.get("sftp_key")
        if datei:
            obj.schluessel_setzen(datei.read().decode("utf-8", errors="replace"))
            return obj.schluessel
        return obj.schluessel if passt else ""


def _html_feld(zeilen=8):
    return forms.Textarea(attrs={"rows": zeilen, "class": "html-eingabe", "dir": "auto",
                                 "data-editor": ""})  # fmt: skip


class RechtstexteForm(forms.ModelForm):
    """Datenschutz, Impressum und Einverständniserklärung als interner Text (ADR 0094)."""

    class Meta:
        model = TafelEinstellungen
        fields = ["datenschutz_text", "impressum_text", "einverstaendnis_text"]
        widgets = {
            "datenschutz_text": _html_feld(10),
            "impressum_text": _html_feld(6),
            "einverstaendnis_text": _html_feld(8),
        }
