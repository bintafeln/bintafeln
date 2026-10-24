"""Formulare: das öffentliche Antragsformular (in der gewählten Sprache) und die Verwaltung."""

from django import forms
from django.contrib.auth import get_user_model
from django.db import transaction

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
from apps.core import privatdateien
from apps.core.auswahl import ANREDEN, FAMILIENSTAENDE, staatsangehoerigkeiten
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
        if einstellungen.angehoerige != Abfrage.AUS:
            for n in range(1, MAX_PERSONEN + 1):
                self.fields[f"p{n}_vorname"] = forms.CharField(
                    label=t["vorname"], max_length=100, required=False)  # fmt: skip
                self.fields[f"p{n}_nachname"] = forms.CharField(
                    label=t["nachname"], max_length=100, required=False)  # fmt: skip
                self.fields[f"p{n}_geburtsdatum"] = forms.DateField(
                    label=t["geburtsdatum"], required=False, widget=DatumEingabe())  # fmt: skip
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

    def _feld(self, name, feld, label, schalter=None):
        abfrage = getattr(self.e, schalter or name)
        if abfrage == Abfrage.AUS:
            return
        feld.label, feld.required = label, abfrage == Abfrage.PFLICHT
        self.fields[name] = feld

    @property
    def personen_zeilen(self):
        """Je weitere Person die drei Felder, für die Tabelle in der Vorlage."""
        if "p1_vorname" not in self.fields:
            return []
        return [
            (n, self.texte["person_n"].format(n=n), self[f"p{n}_vorname"],
             self[f"p{n}_nachname"], self[f"p{n}_geburtsdatum"])
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
        )
        for n in range(1, MAX_PERSONEN + 1):
            if d.get(f"p{n}_vorname"):
                AntragPerson.objects.create(
                    antrag=antrag,
                    vorname=d[f"p{n}_vorname"],
                    nachname=d.get(f"p{n}_nachname", ""),
                    geburtsdatum=d.get(f"p{n}_geburtsdatum"),
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

    class Meta:
        model = AntragEinstellungen
        fields = [
            "aktiv", "modus", *AntragEinstellungen.FELDER, "datenschutz_url", "impressum_url",
            "erklaerungen_url", "voraussetzungen_url", "eigenes_css", "benachrichtigen",
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


def _html_feld(zeilen=8):
    return forms.Textarea(attrs={"rows": zeilen, "class": "html-eingabe", "dir": "auto"})


class TextForm(forms.ModelForm):
    class Meta:
        model = AntragText
        fields = ["ueberschrift", "einleitung", "bestaetigung", "mail_betreff", "mail_text"]
        widgets = {
            "einleitung": _html_feld(),
            "bestaetigung": _html_feld(),
            "mail_text": _html_feld(10),
        }
        help_texts = {
            "einleitung": "Steht über dem Formular. Platzhalter: {tafel}.",
            "bestaetigung": "Erscheint nach dem Absenden unter der Antragsnummer. Platzhalter: "
            "{nummer}, {tafel}.",
            "mail_betreff": "Platzhalter: {nummer}, {tafel}.",
            "mail_text": "Ganzer Inhalt der Antwortmail, wenn ausgefüllt (sonst: Anrede, "
            "Antragsnummer, Text nach dem Absenden, Gruß). Platzhalter: {vorname}, {nachname}, "
            "{nummer}, {tafel}.",
        }
