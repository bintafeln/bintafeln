"""Einkommensart vieler Haushalte auf einmal ändern (ADR 0146).

Beispiel: alle Haushalte mit „Sonstiges“, deren Hauptperson 65 oder älter ist, bekommen
„Grundsicherung“. Zuerst zeigt die Seite nur, wen das betrifft; geändert wird erst auf Knopfdruck.
Welche Einkommensarten und welche Altersgrenze, wählt die Tafel – fest im Programm steht nichts.
Jede Änderung steht in der Historie des Haushalts und im Änderungsprotokoll.
"""

import datetime as dt
import time
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.konten import rollen
from apps.kunden import historie, zugang
from apps.kunden.models import Einkommensart, Haushalt, HaushaltEreignis, Person

RECHT = "kunden.bearbeiten"
SEKUNDEN = 15  # je Aufruf; danach geht es von selbst weiter, damit die Seite nicht hängt
VORSCHAU = 200


class UmstellenForm(forms.Form):
    von = forms.ModelChoiceField(
        label="Haushalte mit Einkommensart", queryset=Einkommensart.objects.none()
    )
    alter = forms.ChoiceField(
        label="Alter der Hauptperson",
        choices=[("ab", "ab … Jahren (so alt oder älter)"), ("unter", "unter … Jahren"),
                 ("alle", "egal")],
        initial="ab",
    )  # fmt: skip
    jahre = forms.IntegerField(label="Jahre", min_value=1, max_value=120, initial=65)
    nach = forms.ModelChoiceField(
        label="bekommen die Einkommensart", queryset=Einkommensart.objects.none()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["von"].queryset = Einkommensart.objects.all()
        self.fields["nach"].queryset = Einkommensart.objects.filter(aktiv=True)

    def clean(self):
        daten = super().clean()
        if daten.get("von") and daten.get("von") == daten.get("nach"):
            raise forms.ValidationError("Bitte zwei verschiedene Einkommensarten wählen.")
        return daten


def grenze(heute: dt.date, jahre: int) -> dt.date:
    """Wer an diesem Tag oder früher geboren ist, ist heute ``jahre`` Jahre alt oder älter."""
    try:
        return heute.replace(year=heute.year - jahre)
    except ValueError:  # 29. Februar
        return heute.replace(year=heute.year - jahre, day=28)


def betroffene(benutzer, von, alter: str, jahre: int, heute: dt.date | None = None):
    """(zu ändernde Haushalte, Haushalte ohne Geburtsdatum der Hauptperson – bleiben, wie sie sind).

    Aktive wie nicht mehr aktive Haushalte; nur Kunden, die das Konto sehen darf (ADR 0034).
    """
    haushalte = zugang.filtern(Haushalt.objects.filter(einkommensart=von), benutzer)
    if alter == "alle":
        return haushalte, haushalte.none()
    haupt = Person.objects.filter(haushalt=OuterRef("pk"), ist_hauptperson=True)
    tag = grenze(heute or timezone.localdate(), jahre)
    passend = (
        haupt.filter(geburtsdatum__lte=tag) if alter == "ab" else haupt.filter(geburtsdatum__gt=tag)
    )
    ohne = haushalte.exclude(Exists(haupt.filter(geburtsdatum__isnull=False)))
    return haushalte.filter(Exists(passend)), ohne


def aendern(haushalte, nach, von: str, sekunden: float | None = None) -> int:
    """Setzt die Einkommensart und hält jede Änderung in der Historie fest; gibt die Zahl zurück.

    Mit ``sekunden`` hört es nach dieser Zeit auf; der Rest kommt beim nächsten Aufruf dran
    (geänderte Haushalte passen dann nicht mehr auf die Auswahl).
    """
    ende = time.monotonic() + sekunden if sekunden else None
    anzahl = 0
    for h in haushalte.order_by("pk").iterator():
        if ende and anzahl and time.monotonic() >= ende:
            break
        with transaction.atomic():
            vorher = historie.schnappschuss(h)
            h.einkommensart = nach
            h.save(update_fields=["einkommensart"])
            Haushalt.objects.filter(pk=h.pk).update(geaendert_am=timezone.now(),
                                                    geaendert_von=von)  # fmt: skip
            historie.festhalten(h.kundennummer, vorher, historie.schnappschuss(h),
                                quelle=HaushaltEreignis.Quelle.BEARBEITUNG, von=von,
                                zusatz="Einkommensart sammelweise geändert")  # fmt: skip
        anzahl += 1
    return anzahl


def _zeilen(haushalte) -> list:
    """Die ersten Haushalte für die Vorschau, mit Name und Geburtsdatum der Hauptperson."""
    zeilen = list(haushalte.order_by("kundennummer")[:VORSCHAU])
    haupt = {p.haushalt_id: p for p in Person.objects.filter(haushalt__in=zeilen,
                                                             ist_hauptperson=True)}  # fmt: skip
    for h in zeilen:
        h.haupt = haupt.get(h.pk)
    return zeilen


@never_cache
@rollen.recht_erforderlich(RECHT)
def umstellen(request):
    daten = request.POST if request.method == "POST" else (request.GET if request.GET else None)
    form = UmstellenForm(daten)
    kontext = {"form": form, "vorschau": VORSCHAU}
    if daten is None or not form.is_valid():
        return render(request, "kunden/einkommensart_umstellen.html", kontext)
    d = form.cleaned_data
    haushalte, ohne = betroffene(request.user, d["von"], d["alter"], d["jahre"])
    if request.method == "POST":
        hier = f"{reverse('kunden:einkommensart_umstellen')}?" + urlencode(
            {k: request.POST.get(k, "") for k in ("von", "alter", "jahre", "nach")}
        )
        anzahl = aendern(haushalte, d["nach"], request.user.get_username(), SEKUNDEN)
        offen = haushalte.count()
        if offen:  # geht in Portionen weiter; die Zahl in der Adresse lädt die Seite sicher neu
            ziel = f"{hier}&laeuft={offen}"
        else:
            messages.success(request, f"Einkommensart geändert: „{d['von']}“ → „{d['nach']}“. "
                             f"Zuletzt {anzahl} Haushalt{'e' if anzahl != 1 else ''}.")  # fmt: skip
            ziel = reverse("kunden:einkommensart_umstellen")
        if request.headers.get("HX-Request"):
            antwort = HttpResponse(status=204)
            antwort["HX-Redirect"] = ziel
            return antwort
        return redirect(ziel)
    kontext.update({
        "gewaehlt": d, "anzahl": haushalte.count(),
        "aktiv": haushalte.filter(status=Haushalt.Status.AKTIV).count(),
        "ohne": ohne.count(), "zeilen": _zeilen(haushalte),
        "laeuft": request.GET.get("laeuft"),
    })  # fmt: skip
    return render(request, "kunden/einkommensart_umstellen.html", kontext)
