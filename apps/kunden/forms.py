from django import forms

from apps.core.auswahl import MERKZEICHEN, merkzeichen_liste
from apps.kunden.models import KundenEinstellungen, Zusatzfeld


class KundenEinstellungenForm(forms.ModelForm):
    export_felder = forms.MultipleChoiceField(
        label="Spalten der Kundenliste und des Exports", required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Erscheinen in „Kunden einsehen“ und in der CSV-Datei; jede Person kann in der "
        "Liste einzelne ausblenden. Leer = Kundennummer, Vorname, Nachname, Kundengruppe, "
        "Ausgabetage, Uhrzeit, Personen, Status, Ausweis, letzter Besuch. Kontaktdaten, "
        "Kontostand und Art.-9-Felder bleiben ohne das passende Recht leer.",
    )  # fmt: skip

    sb_merkzeichen = forms.MultipleChoiceField(
        label=KundenEinstellungen._meta.get_field("sb_merkzeichen").verbose_name, required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=KundenEinstellungen._meta.get_field("sb_merkzeichen").help_text,
    )  # fmt: skip

    class Meta:
        model = KundenEinstellungen
        fields = [
            "telefon_erfassen",
            "email_erfassen",
            "staatsangehoerigkeit_erfassen",
            "familienstand_erfassen",
            "bemerkungen_importieren",
            "kind_bis_alter",
            "ausweis_gueltig_monate",
            "ausweis_bis_monatsende",
            "abholungen_aufbewahren_jahre",
            "zugriffe_aufbewahren_tage",
            "historie_aufbewahren_jahre",
            "gruppe_behalten",
            "export_felder",
            "verlaengern_regel",
            "verlaengern_ab_alter",
            "verlaengern_felder",
            "verlaengern_einkommensarten",
            "verlaengern_ablehnung",
            "verlaengern_sonst_pausieren_monate",
            "verlaengern_fruehestens_tage",
            "krankmeldung",
            "sb_ab_gdb",
            "sb_merkzeichen",
            "sb_ausweis_vorgelegt",
        ]
        widgets = {
            "verlaengern_felder": forms.CheckboxSelectMultiple,
            "verlaengern_einkommensarten": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        from apps.kunden import export

        super().__init__(*args, **kwargs)
        self.fields["export_felder"].choices = export.auswahl()
        self.fields["sb_merkzeichen"].choices = [(c, f"{c} ({b})") for c, b in MERKZEICHEN]
        self.initial["sb_merkzeichen"] = merkzeichen_liste(self.instance.sb_merkzeichen)
        self.initial["export_felder"] = self.instance.export_felder or export.VORGABE

    def clean_sb_merkzeichen(self):
        return ", ".join(merkzeichen_liste(", ".join(self.cleaned_data["sb_merkzeichen"])))

    def clean_export_felder(self):
        from apps.kunden import export

        gewaehlt = set(self.cleaned_data["export_felder"])
        return [k for k, _ in export.auswahl() if k in gewaehlt]


class ZusatzfeldForm(forms.ModelForm):
    class Meta:
        model = Zusatzfeld
        fields = [
            "schluessel",
            "bezeichnung",
            "gilt_fuer",
            "typ",
            "optionen",
            "besondere_kategorie",
            "reihenfolge",
            "aktiv",
            "einlass",
            "ausweis",
            "kuerzel",
        ]
        widgets = {"optionen": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Der Schlüssel verbindet gespeicherte Werte und Importspalte; nicht mehr änderbar.
            self.fields["schluessel"].disabled = True
        if self.instance.fest:
            # Mitgelieferte Merkmale: Art bleibt fest, damit Einlass und Ausweis sie verstehen
            for name in ("gilt_fuer", "typ", "optionen"):
                self.fields[name].disabled = True

    def clean(self):
        daten = super().clean()
        if daten.get("typ") != Zusatzfeld.Typ.JA_NEIN:
            daten["einlass"], daten["ausweis"] = False, ""
        if daten.get("ausweis") == "kuerzel" and not daten.get("kuerzel"):
            self.add_error("kuerzel", "Bitte ein Kürzel für den Ausweis angeben.")
        return daten
