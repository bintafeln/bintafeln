from auditlog.models import LogEntry
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters

from apps.core import sicherung
from apps.core.forms import EinrichtungForm, EinstellungenForm
from apps.core.middleware import admin_existiert
from apps.core.models import TafelEinstellungen
from apps.konten import rollen


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


@login_required
def start(request):
    from apps.ausgabe.konto import buchungsfristen_anwenden
    from apps.kunden.models import ImportVorbereitung, fristen_anwenden

    # Geprüfte, nicht übernommene Importe werden spätestens hier nach einer Stunde gelöscht;
    # Abholungen, Ausnahmen, Zugriffsprotokoll und Buchungen nach ihren Fristen.
    ImportVorbereitung.abgelaufene_loeschen()
    fristen_anwenden()
    buchungsfristen_anwenden()
    kontext = {}
    if rollen.hat_rolle(request.user, rollen.ADMIN):
        kontext["sicherung"] = sicherung.lese_status()
    return render(request, "core/start.html", kontext)


@sensitive_post_parameters("password1", "password2")
def einrichtung(request):
    if admin_existiert():
        raise Http404
    form = EinrichtungForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Sperrt die Einstellungszeile, damit zwei gleichzeitige Einrichtungen
            # nicht zwei Admins anlegen.
            TafelEinstellungen.laden()
            einstellungen = TafelEinstellungen.objects.select_for_update().get(
                pk=TafelEinstellungen.EINZIGE_ID
            )
            if admin_existiert():
                raise Http404
            daten = form.cleaned_data
            admin = get_user_model().objects.create_superuser(
                username=daten["username"], email=daten["email"], password=daten["password1"]
            )
            admin.groups.add(Group.objects.get(name=rollen.ADMIN))
            einstellungen.name = daten["tafel_name"]
            einstellungen.save()
        login(request, admin, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Einrichtung abgeschlossen. Willkommen bei bintafeln!")
        return redirect("core:start")
    return render(request, "core/einrichtung.html", {"form": form})


@rollen.rolle_erforderlich(rollen.ADMIN)
def einstellungen(request):
    instanz = TafelEinstellungen.laden()
    form = EinstellungenForm(request.POST or None, request.FILES or None, instance=instanz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("core:einstellungen")
    return render(request, "core/einstellungen.html", {"form": form})


@rollen.rolle_erforderlich(rollen.ADMIN)
def protokoll(request):
    eintraege = LogEntry.objects.select_related("actor", "content_type").order_by("-timestamp")
    modell = request.GET.get("modell", "")
    if modell.isdigit():
        eintraege = eintraege.filter(content_type_id=int(modell))
    seite = Paginator(eintraege, 50).get_page(request.GET.get("seite"))
    kontext = {
        "seite": seite,
        "modell": modell,
        "modelle": ContentType.objects.filter(
            pk__in=LogEntry.objects.values("content_type").distinct()
        ).order_by("model"),
    }
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "protokoll-liste":
        return render(request, "core/_protokoll_liste.html", kontext)
    return render(request, "core/protokoll.html", kontext)
