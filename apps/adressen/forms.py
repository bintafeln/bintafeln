from django import forms
from django.db.models import Q

from apps.adressen.models import Adresse, AdressKategorie
from apps.core.auswahl import ANREDEN, mit_vorhandenem
from apps.core.forms import Mehrfachauswahl
from apps.konten.forms import DatumEingabe


class AdresseForm(forms.ModelForm):
    anrede = forms.ChoiceField(label="Anrede", required=False)
    webseite = forms.URLField(label="Webseite", required=False, assume_scheme="https")
    kategorien = forms.ModelMultipleChoiceField(
        label="Kategorien", queryset=AdressKategorie.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )  # fmt: skip

    rollen = forms.MultipleChoiceField(
        label="Rollen", required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Die Rollen entscheiden über Rechte und die Einteilung in Dienst-/Fahrdienstplan "
        "(Fahrer/Beifahrer). Jedes Konto braucht mindestens eine Rolle.",
    )  # fmt: skip

    # Angaben zur Mitarbeit hängen am Konto (wie die Rollen) und lassen sich hier mitbearbeiten,
    # damit man dafür nicht in die Team-Liste wechseln muss. ``mitarbeit_felder`` zeigt an, dass die
    # Seite diese Felder überhaupt hatte: Nur dann werden sie gespeichert – sonst leerte eine
    # Anfrage ohne die Felder Ausgabetage und Ausgabestellen.
    mitarbeit_felder = forms.CharField(required=False, widget=forms.HiddenInput, initial="1")
    beschaeftigung = forms.ChoiceField(label="Beschäftigung", required=False)
    ausgabestellen = forms.ModelMultipleChoiceField(
        label="Ausgabestellen", queryset=None, required=False,
        widget=Mehrfachauswahl(leer="keine"),
        help_text="An welchen Ausgabestellen die Person mitarbeitet.",
    )  # fmt: skip
    ausgabetage = forms.MultipleChoiceField(
        label="Ausgabetage", required=False, widget=forms.CheckboxSelectMultiple,
        help_text="An welchen Tagen die Person meist arbeitet; die Kundenliste startet mit diesem "
        "Tag.",
    )  # fmt: skip
    benutzername = forms.CharField(
        label="Benutzername", required=False, max_length=150,
        help_text="Zum Anmelden. Buchstaben, Ziffern und @ . + - _",
    )  # fmt: skip
    MITARBEIT = ("beschaeftigung", "ausgabestellen", "ausgabetage", "benutzername")

    ABSCHNITTE = [
        ("Name", ["art", "organisation", "ansprechperson", "anrede", "vorname", "nachname",
                  "geburtsdatum", "kategorien"]),
        ("Anschrift und Kontakt", ["strasse", "plz", "ort", "land", "telefon", "mobil", "email",
                                   "email_weitere", "webseite"]),
        ("Mitarbeit", ["konto", "rollen", "beschaeftigung", "ausgabestellen", "ausgabetage",
                       "benutzername"]),
        ("Einwilligungen und Notiz", ["einwilligung_post", "einwilligung_email",
                                      "veroeffentlichen", "notiz"]),
    ]  # fmt: skip

    class Meta:
        model = Adresse
        fields = [
            "art", "organisation", "ansprechperson", "anrede", "vorname", "nachname",
            "geburtsdatum", "kategorien",
            "strasse", "plz", "ort", "land", "telefon", "mobil", "email", "email_weitere",
            "webseite", "einwilligung_post", "einwilligung_email", "veroeffentlichen", "notiz",
        ]  # fmt: skip
        widgets = {
            "geburtsdatum": DatumEingabe(),
            "einwilligung_post": DatumEingabe(),
            "einwilligung_email": DatumEingabe(),
            "veroeffentlichen": DatumEingabe(),
            "notiz": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, konto_waehlbar=False, verwalter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.verwalter = verwalter
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, self.instance.anrede)
        # Organisation und Ansprechperson gibt es nur bei einer Organisation (zeigen_bei.js blendet
        # das ganze Feld samt Label ein/aus; ohne JavaScript bleibt alles sichtbar).
        for name in ("organisation", "ansprechperson"):
            self.fields[name].widget.attrs["data-zeigen-bei"] = "art=organisation"
        # Das Geburtsdatum gibt es nur bei einer Person.
        self.fields["geburtsdatum"].widget.attrs["data-zeigen-bei"] = "art=person"
        # Das Konto darf nur verknüpfen, wer Mitarbeitende verwalten darf. Dann auch die Rollen.
        self.rollen_bearbeitbar = konto_waehlbar and verwalter is not None
        if konto_waehlbar:
            from apps.konten.models import Benutzer

            frei = Benutzer.objects.filter(stelle__isnull=True).filter(
                Q(adresse__isnull=True) | Q(adresse=self.instance if self.instance.pk else None)
            )
            self.fields["konto"] = forms.ModelChoiceField(
                label="Konto",
                required=False,
                queryset=frei.order_by("last_name", "first_name"),
                help_text=Adresse._meta.get_field("konto").help_text,
                widget=forms.Select(attrs={"data-zeigen-bei": "art=person"}),
            )
            self.initial.setdefault("konto", self.instance.konto_id)
            if self.instance.pk and self.instance.konto_id:
                # Schon verknüpft: Adresse und Konto gehören fest zusammen. Das Auswahlfeld würde
                # nur verwirren – der Benutzername steht bei „Mitarbeit“. Der Wert reist verdeckt
                # mit, damit die übrige Logik (Rollen, Sperren) unverändert bleibt.
                self.fields["konto"].widget = forms.HiddenInput()
        if self.rollen_bearbeitbar:
            from apps.konten import verwaltung

            self.fields["rollen"].choices = [
                (r, r) for r in verwaltung.vergebbare_rollen(verwalter)
            ]
            self.fields["rollen"].widget.attrs["data-zeigen-bei"] = "art=person"
            konto = self.instance.konto if self.instance.pk else None
            if konto is not None:
                self.initial.setdefault("rollen", list(konto.groups.values_list("name", flat=True)))
            self._mitarbeit_felder(konto)
        else:
            for name in ("rollen", "mitarbeit_felder", *self.MITARBEIT):
                del self.fields[name]
        gewaehlt = list(self.instance.kategorien.values_list("pk", flat=True)) if (
            self.instance.pk) else []  # fmt: skip
        self.fields["kategorien"].queryset = AdressKategorie.objects.filter(
            Q(aktiv=True) | Q(pk__in=gewaehlt)  # gespeicherte bleiben wählbar
        )

    def _seite_veraltet(self) -> bool:
        """Die Maske speichert sofort, ohne neu zu laden (ADR 0145). Legt das erste Häkchen bei
        den Rollen ein Konto an, kennt die offene Seite es noch nicht und schickt weiter „kein
        Konto“. Die Seite nennt deshalb in ``konto_stand``, welches Konto sie beim Laden kannte;
        weicht das vom gespeicherten ab, gilt ihre Angabe zum Konto nicht."""
        if "konto" not in self.fields or "konto_stand" not in self.data:
            return False
        return self.data.get("konto_stand", "") != str(self.instance.konto_id or "")

    def _mitarbeit_felder(self, konto) -> None:
        """Beschäftigung, Ausgabestellen, Ausgabetage und Benutzername des verknüpften Kontos."""
        from apps.ausgabe.ampel import WOCHENTAGE
        from apps.konten.models import Benutzer
        from apps.kunden.models import Ausgabestelle

        gewaehlt = list(konto.ausgabestellen.values_list("pk", flat=True)) if konto else []
        self.fields["beschaeftigung"].choices = Benutzer.Beschaeftigung.choices
        self.fields["ausgabestellen"].queryset = Ausgabestelle.objects.filter(
            Q(aktiv=True) | Q(pk__in=gewaehlt)  # gespeicherte bleiben wählbar
        ).order_by("name")
        self.fields["ausgabetage"].choices = [(t, t) for t in WOCHENTAGE]
        for name in self.MITARBEIT:
            self.fields[name].widget.attrs["data-zeigen-bei"] = "art=person"
        if konto is None:
            # Den Benutzernamen vergibt bintafeln beim Anlegen des Kontos selbst
            del self.fields["benutzername"]
            self.initial.setdefault("beschaeftigung", Benutzer.Beschaeftigung.EHRENAMTLICH)
            return
        # ein halb getippter Benutzername darf nicht gespeichert werden (ADR 0145)
        self.fields["benutzername"].widget.attrs["data-autosave-spaet"] = ""
        self.initial.setdefault("beschaeftigung", konto.beschaeftigung)
        self.initial.setdefault("ausgabestellen", gewaehlt)
        self.initial.setdefault(
            "ausgabetage", [t.strip() for t in (konto.ausgabetage or "").split(",") if t.strip()]
        )
        self.initial.setdefault("benutzername", konto.username)

    def clean_benutzername(self):
        from django.contrib.auth.validators import UnicodeUsernameValidator

        from apps.konten.models import Benutzer

        name = (self.cleaned_data.get("benutzername") or "").strip()
        konto = self.instance.konto if self.instance.pk else None
        if not name or konto is None:
            return ""
        UnicodeUsernameValidator()(name)
        if Benutzer.objects.filter(username__iexact=name).exclude(pk=konto.pk).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return name

    def clean(self):
        cleaned = super().clean()
        if self._seite_veraltet():
            # sonst entstünde je Häkchen ein weiteres Konto, oder das Konto würde gelöst
            cleaned["konto"] = self.instance.konto
        if cleaned.get("art") == Adresse.Art.ORGANISATION and cleaned.get("konto"):
            self.add_error("konto", "Ein Konto gibt es nur bei einer Person.")
        # Jedes aktive Konto braucht mindestens eine Rolle (ADR 0097). Gesperrte (ausgeschiedene)
        # Personen dürfen ohne Rolle geführt werden – so bleiben sie als reine Adresse erhalten.
        if self.rollen_bearbeitbar and cleaned.get("konto") and cleaned["konto"].is_active:
            from apps.konten import verwaltung

            gewaehlt = set(cleaned.get("rollen") or [])
            behalten = set(cleaned["konto"].groups.values_list("name", flat=True)) - set(
                verwaltung.vergebbare_rollen(self.verwalter)
            )
            if not gewaehlt and not behalten:
                self.add_error("rollen", "Jedes aktive Konto braucht mindestens eine Rolle. "
                               "Hört die Person auf? Unten „Person hört auf – Konto sperren“ – "
                               "sie bleibt dann ohne Rolle als Adresse erhalten.")  # fmt: skip
        return cleaned

    def save(self, commit=True):
        # „konto“ ist kein Meta-Feld (nur für Berechtigte da), deshalb von Hand übernehmen.
        if "konto" in self.fields:
            self.instance.konto = self.cleaned_data.get("konto")
        return super().save(commit=commit)

    def rollen_anwenden(self) -> None:
        """Die gewählten Rollen auf das verknüpfte Konto schreiben (nach dem Speichern aufrufen).
        Hat die Person noch kein Konto, aber Rollen gewählt, wird eins angelegt – sonst ginge die
        Rolle verloren, weil Rollen am Konto hängen (ADR 0097)."""
        if not self.rollen_bearbeitbar:
            return
        from apps.konten import verwaltung

        gewaehlt = self.cleaned_data.get("rollen") or []
        if self.instance.konto_id:
            verwaltung.rollen_setzen(self.verwalter, self.instance.konto, gewaehlt)
        elif gewaehlt and self.instance.art == Adresse.Art.PERSON:
            verwaltung.konto_fuer_adresse(self.verwalter, self.instance, gewaehlt)
        # Angaben zur Mitarbeit: nur, wenn die Seite die Felder hatte, und nur mit Konto
        if self.instance.konto_id and self.cleaned_data.get("mitarbeit_felder"):
            from apps.ausgabe.ampel import WOCHENTAGE

            tage = self.cleaned_data.get("ausgabetage") or []
            verwaltung.mitarbeit_setzen(
                self.verwalter, self.instance.konto,
                beschaeftigung=self.cleaned_data.get("beschaeftigung") or "",
                ausgabestellen=self.cleaned_data.get("ausgabestellen"),
                ausgabetage=", ".join(t for t in WOCHENTAGE if t in tage),
                benutzername=self.cleaned_data.get("benutzername") or "",
            )  # fmt: skip

    def abschnitte(self):
        alle = (
            (titel, [self[n] for n in namen if n in self.fields and not self[n].is_hidden])
            for titel, namen in self.ABSCHNITTE
        )
        return [(titel, felder) for titel, felder in alle if felder]


class SammelAdresseForm(forms.ModelForm):
    """Sammelweises Bearbeiten in der Liste: Name, Organisation, Ansprechperson und die
    Mitgliedsnummer bleiben bewusst gesperrt (ADR 0097), damit man beim schnellen Ändern vieler
    Zeilen nicht aus Versehen die Identität verändert. Die Grundfelder (Anschrift, Kontakt) werden
    nur gezeigt, wenn ihre Spalte in der Liste eingeblendet ist; Kategorien, Einwilligungen und
    Notiz stehen immer zur Verfügung."""

    anrede = forms.ChoiceField(label="Anrede", required=False)
    kategorien = forms.ModelMultipleChoiceField(
        label="Kategorien", queryset=AdressKategorie.objects.none(), required=False,
        widget=Mehrfachauswahl,
    )  # fmt: skip

    # Felder, die von der Spaltenwahl der Liste abhängen (Reihenfolge wie in der Liste).
    GRUNDFELDER = ("anrede", "strasse", "plz", "ort", "telefon", "mobil", "email")

    class Meta:
        model = Adresse
        fields = [
            "anrede", "strasse", "plz", "ort", "telefon", "mobil", "email",
            "kategorien", "einwilligung_post", "einwilligung_email", "veroeffentlichen", "notiz",
        ]  # fmt: skip
        widgets = {
            "einwilligung_post": DatumEingabe(),
            "einwilligung_email": DatumEingabe(),
            "veroeffentlichen": DatumEingabe(),
            "notiz": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, spalten=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anrede"].choices = mit_vorhandenem(ANREDEN, self.instance.anrede)
        gewaehlt = (
            list(self.instance.kategorien.values_list("pk", flat=True)) if self.instance.pk else []
        )
        self.fields["kategorien"].queryset = AdressKategorie.objects.filter(
            Q(aktiv=True) | Q(pk__in=gewaehlt)
        )
        if spalten is not None:
            for name in self.GRUNDFELDER:
                if name not in spalten:
                    self.fields.pop(name, None)
        for feld in self.fields.values():
            feld.widget.attrs.setdefault("aria-label", f"{feld.label}: {self.instance}")


class AdressKategorieForm(forms.ModelForm):
    class Meta:
        model = AdressKategorie
        fields = ["name", "aktiv", "reihenfolge"]


class ImportForm(forms.Form):
    datei = forms.FileField(
        label="CSV-Datei",
        help_text="Trennzeichen Semikolon, erste Zeile mit Spaltennamen (siehe Hilfe).",
    )
