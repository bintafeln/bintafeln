from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.core.forms import Mehrfachauswahl
from apps.tickets.models import Kategorie, Ticket, TicketEinstellungen

FOTO_ODER_PDF = "image/jpeg,image/png,image/webp,application/pdf"


class MehrereDateien(forms.FileInput):
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        super().__init__({"accept": FOTO_ODER_PDF, "multiple": True, **(attrs or {})})


class MehrereDateienFeld(forms.FileField):
    def __init__(self, **kwargs):
        super().__init__(widget=MehrereDateien(), required=False, **kwargs)

    def clean(self, data, initial=None):
        dateien = data if isinstance(data, (list, tuple)) else [data]
        return [super(MehrereDateienFeld, self).clean(d, initial) for d in dateien if d]


class TicketForm(forms.ModelForm):
    dateien = MehrereDateienFeld(label="Fotos oder PDF (optional)",
                                 help_text="Z. B. ein Foto vom Schaden; mehrere auf einmal "
                                 "wählbar, je höchstens 5 MB.")  # fmt: skip

    class Meta:
        model = Ticket
        fields = ["kategorie", "titel", "beschreibung"]
        widgets = {"beschreibung": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kategorie"].queryset = Kategorie.objects.filter(aktiv=True)
        self.fields["kategorie"].empty_label = "bitte wählen"


class BearbeitenForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["status", "zustaendig"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        konten = get_user_model().objects.filter(is_active=True, stelle__isnull=True)
        if self.instance.zustaendig_id:  # gespeicherte Wahl bleibt wählbar
            konten = konten | get_user_model().objects.filter(pk=self.instance.zustaendig_id)
        self.fields["zustaendig"].queryset = konten.distinct().order_by("first_name", "username")
        self.fields["zustaendig"].label_from_instance = lambda b: b.get_full_name() or b.username
        self.fields["zustaendig"].empty_label = "niemand"


class KommentarForm(forms.Form):
    text = forms.CharField(label="Antwort oder Notiz", widget=forms.Textarea(attrs={"rows": 3}),
                           max_length=5000)  # fmt: skip


class KategorieForm(forms.ModelForm):
    class Meta:
        model = Kategorie
        fields = ["name", "beschreibung", "personen", "rollen", "aktiv", "reihenfolge"]
        widgets = {
            "personen": Mehrfachauswahl(leer="niemand"),
            "rollen": Mehrfachauswahl(leer="keine Rolle"),
        }
        help_texts = {
            "personen": "Bekommen eine Benachrichtigung bei neuen Tickets dieser Kategorie und "
            "dürfen sie bearbeiten.",
            "rollen": "Alle mit dieser Rolle wie bei „Personen“.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        personen = self.fields["personen"]
        personen.queryset = get_user_model().objects.filter(
            is_active=True, stelle__isnull=True).order_by("first_name", "username")  # fmt: skip
        personen.label_from_instance = lambda b: b.get_full_name() or b.username
        self.fields["rollen"].queryset = Group.objects.filter(rolle__isnull=False).order_by("name")


class EinstellungenForm(forms.ModelForm):
    class Meta:
        model = TicketEinstellungen
        fields = ["loeschen_nach_tagen"]
