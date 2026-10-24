"""Personal: Arbeitsverträge, Urlaub, Krankheit und Stundenkonto (nur Admin und Rolle Personal)."""

from auditlog.signals import accessed
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import privatdateien
from apps.core.models import TafelEinstellungen
from apps.konten import rollen, views_dokumente
from apps.personal import arbeitszeit, berechnung
from apps.personal.forms import AbwesenheitForm, StundenForm, UrlaubsjahrForm, VertragForm
from apps.personal.models import (
    DOKUMENT_ORDNER,
    Abwesenheit,
    Arbeitsvertrag,
    Stunden,
    Urlaubsjahr,
)

personal_erforderlich = rollen.recht_erforderlich("personal.sehen")


def _jahr(request) -> int:
    wert = request.GET.get("jahr") or request.POST.get("jahr") or ""
    jahr = int(wert) if wert.isdigit() else timezone.localdate().year
    return min(max(jahr, 2000), 2100)


def _zurueck(person, jahr):
    return redirect(f"{reverse('personal:person', args=[person.pk])}?jahr={jahr}")


@personal_erforderlich
def liste(request):
    heute = timezone.localdate()
    personen = (
        get_user_model()
        .objects.filter(
            Q(beschaeftigung="fest") | Q(vertraege__isnull=False) | Q(zeitbuchungen__isnull=False)
        )
        .distinct()
        .prefetch_related("vertraege", "abwesenheiten", "urlaubsjahre", "stunden")
        .order_by("-is_active", "last_name", "first_name", "username")
    )
    zeilen = [
        {
            "p": p,
            "vertrag": berechnung.vertrag_am(list(p.vertraege.all()), heute),
            "urlaub": berechnung.urlaub(p, heute.year, heute),
            "saldo": berechnung.stundenkonto(p, heute.year, heute).saldo,
        }
        for p in personen
    ]
    return render(
        request,
        "personal/liste.html",
        {"zeilen": zeilen, "jahr": heute.year, "vergessen": arbeitszeit.vergessen()},
    )


@personal_erforderlich
def person(request, pk):
    p = get_object_or_404(get_user_model(), pk=pk)
    heute, jahr = timezone.localdate(), _jahr(request)
    vertraege = list(p.vertraege.all())
    abweichend = p.urlaubsjahre.filter(jahr=jahr).first()
    return render(
        request,
        "personal/person.html",
        {
            "p": p,
            "jahr": jahr,
            "heute": heute,
            "vertraege": vertraege,
            "aktuell": berechnung.vertrag_am(vertraege, heute),
            "urlaub": berechnung.urlaub(p, jahr, heute),
            "konto": berechnung.stundenkonto(p, jahr, heute),
            "abwesenheiten": [
                (a, berechnung.arbeitstage(a)) for a in p.abwesenheiten.filter(von__year=jahr)
            ],
            "krank_tage": sum(
                (
                    berechnung.arbeitstage(a)
                    for a in p.abwesenheiten.filter(von__year=jahr, art=Abwesenheit.Art.KRANK)
                ),
                berechnung.NULL,
            ),
            "stunden": p.stunden.filter(datum__year=jahr),
            "feiertage_land": TafelEinstellungen.laden().get_bundesland_display(),
            **views_dokumente.kontext(request, p),
            "vertrag_form": VertragForm(),
            "abwesenheit_form": AbwesenheitForm(),
            "stunden_form": StundenForm(initial={"datum": heute}),
            "urlaubsjahr_form": UrlaubsjahrForm(instance=abweichend),
        },
    )


def _fehlertext(form) -> str:
    teile = []
    for feld, fehler in form.errors.items():
        text = " ".join(fehler)
        teile.append(text if feld == "__all__" else f"{form.fields[feld].label}: {text}")
    return "; ".join(teile)


def _speichern(request, pk, form_klasse, text, instanz=None):
    p = get_object_or_404(get_user_model(), pk=pk)
    form = form_klasse(request.POST, instance=instanz)
    if form.is_valid():
        form.instance.benutzer = p
        form.save()
        messages.success(request, text)
    else:
        messages.error(request, f"Nicht gespeichert. {_fehlertext(form)}")
    return _zurueck(p, _jahr(request))


@require_POST
@personal_erforderlich
def vertrag_neu(request, pk):
    return _speichern(request, pk, VertragForm, "Arbeitsvertrag eingetragen.")


@personal_erforderlich
def vertrag_bearbeiten(request, pk, vertrag):
    v = get_object_or_404(Arbeitsvertrag, pk=vertrag, benutzer_id=pk)
    form = VertragForm(request.POST or None, instance=v)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Arbeitsvertrag gespeichert.")
        return _zurueck(v.benutzer, v.beginn.year)
    return render(request, "personal/vertrag.html", {"form": form, "v": v, "p": v.benutzer})


@require_POST
@personal_erforderlich
def vertrag_loeschen(request, pk, vertrag):
    v = get_object_or_404(Arbeitsvertrag, pk=vertrag, benutzer_id=pk)
    privatdateien.loeschen(DOKUMENT_ORDNER, v.dokument_datei)
    v.delete()
    messages.success(request, "Arbeitsvertrag gelöscht.")
    return _zurueck(v.benutzer, _jahr(request))


@require_POST
@personal_erforderlich
def dokument_hochladen(request, pk, vertrag):
    v = get_object_or_404(Arbeitsvertrag, pk=vertrag, benutzer_id=pk)
    datei = request.FILES.get("dokument")
    try:
        if datei is None:
            raise privatdateien.DateiFehler("Bitte eine Datei auswählen.")
        name = privatdateien.speichern(DOKUMENT_ORDNER, datei, max_mb=10)
    except privatdateien.DateiFehler as fehler:
        messages.error(request, str(fehler))
    else:
        privatdateien.loeschen(DOKUMENT_ORDNER, v.dokument_datei)
        v.dokument_datei, v.dokument_typ = name, datei.content_type
        v.save()
        messages.success(request, "Vertragsdokument verschlüsselt gespeichert.")
    return redirect("personal:vertrag", pk=pk, vertrag=v.pk)


@never_cache
@personal_erforderlich
def dokument_ansehen(request, pk, vertrag):
    v = get_object_or_404(Arbeitsvertrag, pk=vertrag, benutzer_id=pk)
    inhalt = privatdateien.lesen(DOKUMENT_ORDNER, v.dokument_datei)
    if inhalt is None:
        raise Http404
    accessed.send(sender=Arbeitsvertrag, instance=v)  # Abruf im Änderungsprotokoll
    antwort = HttpResponse(inhalt, content_type=v.dokument_typ)
    antwort["Content-Disposition"] = "inline"
    return antwort


@require_POST
@personal_erforderlich
def dokument_loeschen(request, pk, vertrag):
    v = get_object_or_404(Arbeitsvertrag, pk=vertrag, benutzer_id=pk)
    privatdateien.loeschen(DOKUMENT_ORDNER, v.dokument_datei)
    v.dokument_datei = v.dokument_typ = ""
    v.save()
    messages.success(request, "Vertragsdokument gelöscht.")
    return redirect("personal:vertrag", pk=pk, vertrag=v.pk)


@require_POST
@personal_erforderlich
def abwesenheit_neu(request, pk):
    return _speichern(request, pk, AbwesenheitForm, "Abwesenheit eingetragen.")


@require_POST
@personal_erforderlich
def urlaubsjahr(request, pk):
    p = get_object_or_404(get_user_model(), pk=pk)
    jahr = _jahr(request)
    instanz = Urlaubsjahr.objects.filter(benutzer=p, jahr=jahr).first() or Urlaubsjahr(jahr=jahr)
    return _speichern(request, pk, UrlaubsjahrForm, f"Urlaubsjahr {jahr} gespeichert.", instanz)


@require_POST
@personal_erforderlich
def stunden_neu(request, pk):
    return _speichern(request, pk, StundenForm, "Stunden eingetragen.")


@require_POST
@personal_erforderlich
def eintrag_loeschen(request, pk, art, eintrag):
    modell = {"abwesenheit": Abwesenheit, "stunden": Stunden}.get(art)
    if modell is None:
        raise Http404
    get_object_or_404(modell, pk=eintrag, benutzer_id=pk).delete()
    messages.success(request, "Eintrag gelöscht.")
    return _zurueck(get_object_or_404(get_user_model(), pk=pk), _jahr(request))
