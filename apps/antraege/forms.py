"""Formulare: das öffentliche Antragsformular (in der gewählten Sprache) und die Verwaltung."""

from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.antraege import gebiet, sprachen
from apps.antraege.models import (
    ANHANG_ORDNER,
    Abfrage,
    Antrag,
    AntragAnhang,
    AntragEinstellungen,
    AntragPerson,
    AntragText,
)
from apps.ausgabe.ampel import WOCHENTAGE
from apps.core import geheimnis, privatdateien
from apps.core.auswahl import (
    ANREDEN,
    FAMILIENSTAENDE,
    GDB_STUFEN,
    MERKZEICHEN,
    MERKZEICHEN_CODES,
    gdb_text,
    merkzeichen_auswahl,
    merkzeichen_liste,
    mit_vorhandenem,
    staatsangehoerigkeiten,
)
from apps.core.forms import StaatAuswahl
from apps.konten.forms import DatumEingabe
from apps.kunden.models import Ausgabestelle

MAX_PERSONEN = 8
MAX_ANHAENGE = 5
MAX_MB = 10
ANHANG_TYPEN = {"image/jpeg", "image/png", "application/pdf"}
TAGE = WOCHENTAGE[:6]  # Mo–Sa
FAMILIENSTAND_TEXT = dict(zip(FAMILIENSTAENDE, ["fs_ledig", "fs_verheiratet", "fs_partnerschaft",
                                                "fs_getrennt", "fs_geschieden", "fs_verwitwet"],
                              strict=True))  # fmt: skip


def _zahl(wert) -> int | None:
    return int(wert) if wert not in (None, "") else None


def _merkzeichen(gdb, gewaehlt) -> str:
    """Merkzeichen nur zusammen mit einem GdB über 0, in fester Reihenfolge."""
    if not _zahl(gdb):
        return ""
    return ", ".join(c for c in MERKZEICHEN_CODES if c in (gewaehlt or []))


def _merkzeichen_feld(label, choices) -> forms.MultipleChoiceField:
    return forms.MultipleChoiceField(label=label, choices=choices, required=False,
                                     widget=forms.CheckboxSelectMultiple)  # fmt: skip


class MehrereDateien(forms.ClearableFileInput):
    allow_multiple_selected = True


class MehrereDateienFeld(forms.FileField):
    widget = MehrereDateien

    def clean(self, daten, initial=None):
        if not daten:
            return super().clean(None, initial) or []
        dateien = daten if isinstance(daten, list | tuple) else [daten]
        return [super(MehrereDateienFeld, self).clean(d, initial) for d in dateien]


class AntragForm(forms.Form):
    """Baut die Felder nach den Einstellungen der Tafel und in der Sprache ``texte``."""

    def __init__(self, *args, texte: dict, einstellungen: AntragEinstellungen, **kwargs):
        super().__init__(*args, **kwargs)
        self.texte, self.e = texte, einstellungen
        t = texte
        modus = einstellungen.modus
        if modus == AntragEinstellungen.Modus.BEIDES:
            self.fields["art"] = forms.ChoiceField(
                label=t["art"], widget=forms.RadioSelect, initial=Antrag.Art.NEU,
                choices=[(Antrag.Art.NEU, t["art_neu"]),
                         (Antrag.Art.VERLAENGERUNG, t["art_verlaengerung"])],
            )  # fmt: skip
        if modus != AntragEinstellungen.Modus.NEU:
            self._feld("kundennummer", forms.CharField(max_length=20), t["kundennummer"])
        self._feld("anrede", forms.ChoiceField(choices=[
            (wert, t["keine_angabe"] if not wert else t[f"anrede_{wert.lower()}"])
            for wert, _ in ANREDEN]), t["anrede"])  # fmt: skip
        self.fields["vorname"] = forms.CharField(label=t["vorname"], max_length=100)
        self.fields["nachname"] = forms.CharField(label=t["nachname"], max_length=100)
        self._feld("geburtsdatum", forms.DateField(widget=DatumEingabe()), t["geburtsdatum"])
        for name, laenge in (("strasse", 200), ("plz", 10), ("ort", 100)):
            self._feld(name, forms.CharField(max_length=laenge), t[name], schalter="anschrift")
        self._feld("telefon", forms.CharField(max_length=50), t["telefon"])
        self._feld("email", forms.EmailField(help_text=t["email_hilfe"]), t["email"])
        familienstaende = [(w, t[FAMILIENSTAND_TEXT[w]]) for w in FAMILIENSTAENDE]
        self._feld(
            "familienstand",
            forms.ChoiceField(choices=[("", t["keine_angabe"]), *familienstaende]),
            t["familienstand"],
        )
        staaten = [(w, {"staatenlos": t["staatenlos"], "ungeklärt": t["ungeklaert"]}.get(w, n))
                   for w, n in staatsangehoerigkeiten(t["keine_angabe"])]  # fmt: skip
        self._feld("staatsangehoerigkeit", forms.ChoiceField(choices=staaten, widget=StaatAuswahl),
                   t["staatsangehoerigkeit"])  # fmt: skip
        # Grad der Behinderung als Auswahl; bei Pflicht muss „keine Behinderung“ gewählt werden
        gdb = [("0", t["behinderung_nein"])] + [(str(n), t["gdb_stufe"].format(n=n))
                                                for n in GDB_STUFEN]  # fmt: skip
        self._feld("gdb", forms.ChoiceField(choices=[("", t["keine_angabe"]), *gdb]),
                   t["behinderung"], schalter="behinderung")  # fmt: skip
        # Merkzeichen (mehrere möglich), nur zusammen mit einem GdB; auf Deutsch mit Bedeutung
        deutsch = t["merkzeichen"] == sprachen.texte("de")["merkzeichen"]
        merkzeichen = [(c, f"{c} ({b})" if deutsch else c) for c, b in MERKZEICHEN]
        if "gdb" in self.fields:
            self.fields["merkzeichen"] = _merkzeichen_feld(t["merkzeichen"], merkzeichen)
        if einstellungen.angehoerige != Abfrage.AUS:
            for n in range(1, MAX_PERSONEN + 1):
                self.fields[f"p{n}_vorname"] = forms.CharField(
                    label=t["vorname"], max_length=100, required=False)  # fmt: skip
                self.fields[f"p{n}_nachname"] = forms.CharField(
                    label=t["nachname"], max_length=100, required=False)  # fmt: skip
                self.fields[f"p{n}_geburtsdatum"] = forms.DateField(
                    label=t["geburtsdatum"], required=False, widget=DatumEingabe())  # fmt: skip
                if einstellungen.behinderung != Abfrage.AUS:
                    self.fields[f"p{n}_gdb"] = forms.ChoiceField(
                        label=t["behinderung"], choices=[("", t["keine_angabe"]), *gdb],
                        required=False)  # fmt: skip
                    self.fields[f"p{n}_merkzeichen"] = _merkzeichen_feld(t["merkzeichen"],
                                                                         merkzeichen)  # fmt: skip
                if einstellungen.staatsangehoerigkeit != Abfrage.AUS:  # nicht immer wie Person 1
                    self.fields[f"p{n}_staatsangehoerigkeit"] = forms.ChoiceField(
                        label=t["staatsangehoerigkeit"], choices=staaten, required=False,
                        widget=StaatAuswahl)  # fmt: skip
        self._feld("wochentage", forms.MultipleChoiceField(
            widget=forms.CheckboxSelectMultiple,
            choices=[(tag, t[f"tag_{tag.lower()}"]) for tag in TAGE]), t["wochentage"])  # fmt: skip
        stellen = Ausgabestelle.objects.filter(aktiv=True).values_list("name", flat=True)
        self._feld("ausgabestelle", forms.ChoiceField(
            choices=[("", t["egal"])] + [(s, s) for s in stellen]), t["ausgabestelle"])  # fmt: skip
        hilfe = t["anhaenge_hilfe"].format(anzahl=MAX_ANHAENGE, mb=MAX_MB)
        self._feld("anhaenge", MehrereDateienFeld(help_text=hilfe), t["anhaenge"])
        self._feld("nachricht", forms.CharField(widget=forms.Textarea(attrs={"rows": 4}),
                                                max_length=2000), t["nachricht"])  # fmt: skip
        if einstellungen.einwilligung_abfragen:
            self.fields["einwilligung"] = forms.BooleanField(
                label=t["einwilligung"], error_messages={"required": t["fehler_einwilligung"]}
            )
        # Für Menschen unsichtbar; wer es ausfüllt, ist sehr wahrscheinlich ein Programm.
        self.fields["webseite"] = forms.CharField(required=False, label="Webseite")
        for feld in self.fields.values():
            feld.error_messages.update(
                {
                    "required": feld.error_messages.get("required")
                    if feld.label == t["einwilligung"]
                    else t["fehler_pflicht"],
                    "invalid": t["fehler_email"]
                    if isinstance(feld, forms.EmailField)
                    else t["fehler_datum"],
                    "invalid_choice": t["fehler_auswahl"],
                    "max_length": t["fehler_formular"],
                }
            )
        # Pflicht-Häkchen zu den Erklärungen, je nach Einstellung (Vorgabe: alle)
        for name, abfragen in (
            ("datenschutz_bestaetigt", einstellungen.datenschutz_abfragen),
            ("einverstaendnis_bestaetigt", einstellungen.einverstaendnis_abfragen),
        ):
            if abfragen:
                self.fields[name] = forms.BooleanField(
                    label=t[name], error_messages={"required": t["fehler_bestaetigen"]}
                )

    def _feld(self, name, feld, label, schalter=None):
        abfrage = getattr(self.e, schalter or name)
        if abfrage == Abfrage.AUS:
            return
        feld.label, feld.required = label, abfrage == Abfrage.PFLICHT
        self.fields[name] = feld

    @property
    def personen_zeilen(self):
        """Je weitere Person ihre Felder (Staatsangehörigkeit und GdB nur, wenn abgefragt)."""
        if "p1_vorname" not in self.fields:
            return []

        def wenn(name):
            return self[name] if name in self.fields else None

        return [
            (n, self.texte["person_n"].format(n=n), self[f"p{n}_vorname"],
             self[f"p{n}_nachname"], self[f"p{n}_geburtsdatum"],
             wenn(f"p{n}_staatsangehoerigkeit"), wenn(f"p{n}_gdb"), wenn(f"p{n}_merkzeichen"))
            for n in range(1, MAX_PERSONEN + 1)
        ]  # fmt: skip

    @property
    def ist_bot(self) -> bool:
        return bool(self.data.get("webseite"))

    def art(self) -> str:
        if self.e.modus == AntragEinstellungen.Modus.BEIDES:
            return self.cleaned_data["art"]
        return self.e.modus

    def clean(self):
        daten = super().clean()
        t = self.texte
        for n in range(1, MAX_PERSONEN + 1):
            if (daten.get(f"p{n}_nachname") or daten.get(f"p{n}_geburtsdatum")) and not daten.get(
                f"p{n}_vorname"
            ):
                self.add_error(f"p{n}_vorname", t["fehler_pflicht"])
        dateien = daten.get("anhaenge") or []
        if len(dateien) > MAX_ANHAENGE:
            self.add_error("anhaenge", t["fehler_datei_anzahl"].format(anzahl=MAX_ANHAENGE))
        elif any(d.content_type not in ANHANG_TYPEN for d in dateien):
            self.add_error("anhaenge", t["fehler_datei_typ"])
        elif any(d.size > MAX_MB * 1024 * 1024 for d in dateien):
            self.add_error("anhaenge", t["fehler_datei_gross"].format(mb=MAX_MB))
        if (
            self.e.gebiet_pruefen == AntragEinstellungen.Gebiet.SPERREN
            and gebiet.passt(self.e, daten.get("plz"), daten.get("ort")) is False
        ):
            self.add_error("plz", t["fehler_gebiet"].format(gebiet=gebiet.name(self.e)))
        return daten

    @transaction.atomic
    def speichern(self, sprache: str) -> Antrag:
        d = self.cleaned_data
        art = self.art()
        antrag = Antrag.objects.create(
            art=art,
            sprache=sprache,
            kundennummer=d.get("kundennummer", "") if art == Antrag.Art.VERLAENGERUNG else "",
            **{
                feld: d.get(feld) or ("" if feld != "geburtsdatum" else None)
                for feld in (
                    "anrede",
                    "vorname",
                    "nachname",
                    "geburtsdatum",
                    "strasse",
                    "plz",
                    "ort",
                    "telefon",
                    "email",
                    "familienstand",
                    "staatsangehoerigkeit",
                    "ausgabestelle",
                    "nachricht",
                )
            },  # fmt: skip
            wochentage=", ".join(d.get("wochentage") or []),
            gdb=_zahl(d.get("gdb")),
            merkzeichen=_merkzeichen(d.get("gdb"), d.get("merkzeichen")),
            einwilligung_bestaetigt=bool(d.get("einwilligung")),
            datenschutz_bestaetigt=bool(d.get("datenschutz_bestaetigt")),
            einverstaendnis_bestaetigt=bool(d.get("einverstaendnis_bestaetigt")),
        )
        for n in range(1, MAX_PERSONEN + 1):
            if d.get(f"p{n}_vorname"):
                AntragPerson.objects.create(
                    antrag=antrag,
                    vorname=d[f"p{n}_vorname"],
                    nachname=d.get(f"p{n}_nachname", ""),
                    geburtsdatum=d.get(f"p{n}_geburtsdatum"),
                    staatsangehoerigkeit=d.get(f"p{n}_staatsangehoerigkeit") or "",
                    gdb=_zahl(d.get(f"p{n}_gdb")),
                    merkzeichen=_merkzeichen(d.get(f"p{n}_gdb"), d.get(f"p{n}_merkzeichen")),
                )
        for datei in d.get("anhaenge") or []:
            AntragAnhang.objects.create(
                antrag=antrag,
                name=datei.name[:200],
                datei=privatdateien.speichern(
                    ANHANG_ORDNER, datei, typen=ANHANG_TYPEN, max_mb=MAX_MB
                ),  # fmt: skip
                typ=datei.content_type,
                groesse=datei.size,
            )
        return antrag


# --- Verwaltung -------------------------------------------------------------------------


class EinstellungenForm(forms.ModelForm):
    # Links ohne Schema (z. B. "tafel.example.org/datenschutz") als https lesen.
    datenschutz_url = forms.URLField(
        label="Link zur Datenschutzerklärung", required=False, assume_scheme="https"
    )
    impressum_url = forms.URLField(
        label="Link zum Impressum", required=False, assume_scheme="https"
    )
    erklaerungen_url = forms.URLField(
        label="Link zu Erklärungen", required=False, assume_scheme="https",
        help_text=AntragEinstellungen._meta.get_field("erklaerungen_url").help_text,
    )  # fmt: skip
    voraussetzungen_url = forms.URLField(
        label="Link zu Voraussetzungen", required=False, assume_scheme="https",
        help_text=AntragEinstellungen._meta.get_field("voraussetzungen_url").help_text,
    )  # fmt: skip

    einverstaendnis_url = forms.URLField(
        label="Link zur Einverständniserklärung", required=False, assume_scheme="https",
        help_text=AntragEinstellungen._meta.get_field("einverstaendnis_url").help_text,
    )  # fmt: skip

    ki_schluessel = forms.CharField(
        label="API-Schlüssel für die KI-Übersetzung (Claude)", required=False, strip=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Eigener Schlüssel von console.anthropic.com. Leer lassen, um den gespeicherten "
        "zu behalten. Er wird verschlüsselt gespeichert und nie wieder angezeigt. Übersetzt werden "
        "nur die eigenen Texte, nie Angaben aus Anträgen.",
    )  # fmt: skip
    ki_schluessel_loeschen = forms.BooleanField(label="Gespeicherten Schlüssel löschen",
                                                required=False)  # fmt: skip

    class Meta:
        model = AntragEinstellungen
        fields = [
            "aktiv", "modus", "erste_nummer", *AntragEinstellungen.FELDER,
            "einwilligung_abfragen", "datenschutz_abfragen", "einverstaendnis_abfragen",
            "gebiet_pruefen", "gebiet_plz", "gebiet_orte", "gebiet_name",
            "datenschutz_url",
            "impressum_url", "erklaerungen_url", "voraussetzungen_url", "einverstaendnis_url",
            "kopf_zeigen", "ueberschrift_zeigen", "fuss_zeigen",
            "eigenes_css", "benachrichtigen",
            "erledigt_nach_tagen", "papierkorb_nach_tagen", "loeschen_nach_tagen",
        ]  # fmt: skip
        widgets = {
            "benachrichtigen": forms.CheckboxSelectMultiple,
            "eigenes_css": forms.Textarea(attrs={"rows": 4, "class": "html-eingabe"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Auswahl statt Freitext: nur aktive Mitarbeitende mit E-Mail-Adresse.
        self.fields["benachrichtigen"].queryset = (
            get_user_model()
            .objects.filter(is_active=True)
            .exclude(email="")
            .order_by("last_name", "first_name", "username")
        )

    def save(self, commit=True):
        instanz = super().save(commit=False)
        if self.cleaned_data.get("ki_schluessel_loeschen"):
            instanz.ki_schluessel_verschluesselt = ""
        elif self.cleaned_data.get("ki_schluessel"):
            instanz.ki_schluessel_verschluesselt = geheimnis.verschluesseln(
                self.cleaned_data["ki_schluessel"]
            )
        if commit:
            instanz.save()
            self.save_m2m()
        return instanz


def _html_feld(zeilen=8):
    return forms.Textarea(attrs={"rows": zeilen, "class": "html-eingabe", "dir": "auto",
                                 "data-editor": ""})  # fmt: skip


class TextForm(forms.ModelForm):
    class Meta:
        model = AntragText
        fields = ["kopf", "ueberschrift", "einleitung", "anhaenge_hinweis", "bestaetigung",
                  "mail_betreff", "mail_text", "fuss"]  # fmt: skip
        widgets = {
            "kopf": _html_feld(4),
            "fuss": _html_feld(4),
            "anhaenge_hinweis": _html_feld(3),
            "einleitung": _html_feld(),
            "bestaetigung": _html_feld(),
            "mail_text": _html_feld(10),
        }
        help_texts = {
            "kopf": "Steht ganz oben unter der Kopfzeile, auf allen Seiten des Formulars, z. B. "
            "ein Bild oder ein farbiges Band. Leer in einer Sprache = der deutsche. Platzhalter: "
            "{tafel}.",
            "fuss": "Steht ganz unten über der Fußzeile, z. B. Anschrift, Öffnungszeiten, "
            "Telefon. Leer in einer Sprache = der deutsche. Platzhalter: {tafel}.",
            "ueberschrift": "Ob sie erscheint, stellen Sie unter „Anträge einstellen“ ein.",
            "einleitung": "Steht über dem Formular. Platzhalter: {tafel}.",
            "anhaenge_hinweis": "Steht über dem Feld für die Nachweise, z. B. welche Unterlagen "
            "nötig sind. Leer in einer Sprache = der deutsche Hinweis.",
            "bestaetigung": "Erscheint nach dem Absenden. Platzhalter: {tafel} (die Antragsnummer "
            "zeigt die Seite bewusst nicht).",
            "mail_betreff": "Platzhalter: {tafel}.",
            "mail_text": "Ganzer Inhalt der Antwortmail, wenn ausgefüllt (sonst: Anrede, "
            "„Ihr Antrag ist eingegangen“, Text nach dem Absenden, Gruß). Platzhalter: {vorname}, "
            "{nachname}, {tafel}. Die Antragsnummer steht nie in der Mail. Die Mail kommt auf "
            "Deutsch und darunter in der Sprache zur angegebenen Staatsangehörigkeit.",
        }


class MerkzeichenMixin:
    """Merkzeichen als Mehrfachauswahl; gespeichert als Text „G, B“."""

    def _merkzeichen_einrichten(self):
        self.fields["merkzeichen"] = forms.MultipleChoiceField(
            label="Merkzeichen", required=False, widget=forms.CheckboxSelectMultiple,
            choices=[(c, f"{c} ({b})") for c, b in merkzeichen_auswahl(self.instance.merkzeichen)],
            initial=merkzeichen_liste(self.instance.merkzeichen),
        )  # fmt: skip

    def clean_merkzeichen(self):
        return ", ".join(merkzeichen_liste(", ".join(self.cleaned_data["merkzeichen"])))


def _gdb_feld() -> forms.TypedChoiceField:
    return forms.TypedChoiceField(
        label="Behinderung", required=False, coerce=int, empty_value=None,
        choices=[("", "keine Angabe")] + [(n, gdb_text(n)) for n in [0, *GDB_STUFEN]],
    )  # fmt: skip


class AntragBearbeitenForm(MerkzeichenMixin, forms.ModelForm):
    """Angaben eines Antrags korrigieren (Büro, Admin); Auswahl statt Freitext wie im Formular."""

    anrede = forms.ChoiceField(label="Anrede", required=False, choices=ANREDEN)
    familienstand = forms.ChoiceField(label="Familienstand", required=False)
    staatsangehoerigkeit = forms.ChoiceField(
        label="Staatsangehörigkeit", required=False, widget=StaatAuswahl
    )
    gdb = _gdb_feld()

    class Meta:
        model = Antrag
        fields = [
            "art", "kundennummer", "anrede", "vorname", "nachname", "geburtsdatum", "strasse",
            "plz", "ort", "telefon", "email", "familienstand", "staatsangehoerigkeit", "gdb",
            "merkzeichen", "wochentage", "ausgabestelle", "nachricht",
        ]  # fmt: skip
        widgets = {"geburtsdatum": DatumEingabe(), "nachricht": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        a = self.instance
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, a.anrede)
        self.fields["familienstand"].choices = mit_vorhandenem(
            [("", "—")] + [(f, f) for f in FAMILIENSTAENDE], a.familienstand
        )
        self.fields["staatsangehoerigkeit"].choices = mit_vorhandenem(
            staatsangehoerigkeiten(), a.staatsangehoerigkeit
        )
        self._merkzeichen_einrichten()


class AntragPersonForm(MerkzeichenMixin, forms.ModelForm):
    staatsangehoerigkeit = forms.ChoiceField(
        label="Staatsangehörigkeit", required=False, widget=StaatAuswahl
    )

    gdb = _gdb_feld()

    class Meta:
        model = AntragPerson
        fields = [
            "vorname",
            "nachname",
            "geburtsdatum",
            "staatsangehoerigkeit",
            "gdb",
            "merkzeichen",
        ]
        widgets = {"geburtsdatum": DatumEingabe()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["staatsangehoerigkeit"].choices = mit_vorhandenem(
            staatsangehoerigkeiten(), self.instance.staatsangehoerigkeit
        )
        self._merkzeichen_einrichten()


AntragPersonenFormset = forms.inlineformset_factory(
    Antrag, AntragPerson, form=AntragPersonForm, extra=2, can_delete=True
)
