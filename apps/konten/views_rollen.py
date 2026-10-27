"""Rollen und Rechte verwalten (ADR 0033).

Wer nicht Admin ist, kann nur Rechte vergeben oder entziehen, die er selbst hat; Rechte einer
Rolle, die er nicht hat, bleiben unverändert. Die Rolle Admin hat immer alle Rechte und lässt
sich weder ändern noch löschen (außer Beschreibung und Zwei-Faktor durch einen Admin).
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core import module, papierkorb
from apps.konten import rechte as katalog
from apps.konten import rollen
from apps.konten.models import Rolle

verwalten = rollen.recht_erforderlich("einstellungen.rollen")


class RolleForm(forms.ModelForm):
    name = forms.CharField(label="Name", max_length=150)
    rechte = forms.MultipleChoiceField(
        label="Rechte", required=False, widget=forms.CheckboxSelectMultiple
    )

    field_order = ["name", "beschreibung"]

    class Meta:
        model = Rolle
        fields = ["beschreibung", "zwei_faktor_pflicht", "braucht_belehrung",
                  "braucht_fuehrerschein", "reihenfolge"]  # fmt: skip

    def __init__(self, *args, eigene, **kwargs):
        super().__init__(*args, **kwargs)
        # Nur Rechte, die man selbst hat, lassen sich ändern; Rechte ausgeschalteter Module
        # bleiben unsichtbar und unverändert.
        self.eigene = eigene - module.ausgeschaltete_rechte()
        self.fields["rechte"].choices = [(r.code, r.bezeichnung) for r in katalog.KATALOG
                                         if r.code in self.eigene]  # fmt: skip
        if self.instance.pk:
            self.fields["name"].initial = self.instance.name
            self.fields["rechte"].initial = [c for c in self.instance.rechte if c in self.eigene]
        if self.instance.pk and self.instance.ist_admin:
            self.fields["name"].disabled = True
            del self.fields["rechte"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        andere = Group.objects.filter(name__iexact=name)
        if self.instance.pk:
            andere = andere.exclude(pk=self.instance.gruppe_id)
        if andere.exists():
            raise forms.ValidationError("Eine Rolle mit diesem Namen gibt es schon.")
        if name.lower() == rollen.ADMIN.lower() and not (
            self.instance.pk and self.instance.ist_admin
        ):
            raise forms.ValidationError("Der Name „Admin“ ist der Admin-Rolle vorbehalten.")
        return name

    @transaction.atomic
    def save(self, commit=True):
        rolle = super().save(commit=False)
        if rolle.pk:
            gruppe = rolle.gruppe
            if not rolle.ist_admin:
                gruppe.name = self.cleaned_data["name"]
                gruppe.save()
        else:
            gruppe = Group.objects.create(name=self.cleaned_data["name"])
            rolle = Rolle.objects.get(gruppe=gruppe)  # vom Signal angelegt
            for feld in self._meta.fields:
                setattr(rolle, feld, self.cleaned_data[feld])
        if "rechte" in self.fields:
            fremde = [c for c in rolle.rechte if c not in self.eigene]  # bleiben unverändert
            gewaehlt = set(self.cleaned_data["rechte"]) | set(fremde)
            rolle.rechte = [r.code for r in katalog.KATALOG if r.code in gewaehlt]
        rolle.save()
        return rolle


def _darf_aendern(request, rolle) -> bool:
    return not rolle.ist_admin or rollen.ist_admin(request.user)


@verwalten
def liste(request):
    eintraege = Rolle.objects.select_related("gruppe").annotate(
        mitglieder=Count("gruppe__user", distinct=True)
    )
    return render(
        request, "konten/rollen.html", {"eintraege": eintraege, "anzahl": len(katalog.ALLE)}
    )


@verwalten
def bearbeiten(request, pk=None):
    rolle = get_object_or_404(Rolle.objects.select_related("gruppe"), pk=pk) if pk else Rolle()
    if pk and not _darf_aendern(request, rolle):
        raise PermissionDenied
    form = RolleForm(
        request.POST or None,
        instance=rolle,
        eigene=rollen.rechte_von(request.user),
    )
    if request.method == "POST" and form.is_valid():
        rolle = form.save()
        messages.success(request, f"Rolle „{rolle}“ gespeichert.")
        return redirect("konten:rollen")
    bereiche = []
    if "rechte" in form.fields:
        gewaehlt = set(form["rechte"].value() or [])
        eigene = rollen.rechte_von(request.user)
        for titel, eintraege in katalog.bereiche():
            bereiche.append((titel, [
                {"recht": r, "gewaehlt": r.code in gewaehlt or r.code in rolle.rechte
                 and r.code not in eigene, "aenderbar": r.code in eigene}
                for r in eintraege
            ]))  # fmt: skip
    return render(
        request,
        "konten/rolle.html",
        {"form": form, "rolle": rolle if pk else None, "bereiche": bereiche},
    )


@require_POST
@verwalten
def loeschen(request, pk):
    rolle = get_object_or_404(Rolle.objects.select_related("gruppe"), pk=pk)
    if rolle.ist_admin:
        raise PermissionDenied
    if not set(rolle.rechte) <= rollen.rechte_von(request.user):
        messages.error(request, "Diese Rolle hat Rechte, die Sie nicht haben, und bleibt.")
        return redirect("konten:rollen")
    name, anzahl = rolle.name, rolle.gruppe.user_set.count()
    # Die Gruppe löscht die Rolle und die Zuordnung zu den Konten mit; alles in den Papierkorb
    papierkorb.loeschen(request.user, "Rolle", name, rolle.gruppe, recht="einstellungen.rollen")
    messages.success(request, f"Rolle „{name}“ in den Papierkorb gelegt ({anzahl} Konto/Konten "
                              "ohne diese Rolle).")  # fmt: skip
    return redirect("konten:rollen")
