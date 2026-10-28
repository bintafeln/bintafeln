from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import papierkorb
from apps.konten import rollen
from apps.links.forms import GruppeForm, LinkForm
from apps.links.models import Link, LinkGruppe

pflegen = rollen.recht_erforderlich("einstellungen.links")


@never_cache
@pflegen
def liste(request):
    return render(request, "links/liste.html", {
        "links": Link.objects.select_related("gruppe").order_by(
            "gruppe__reihenfolge", "gruppe__titel", "reihenfolge", "titel"),
        "gruppen": LinkGruppe.objects.all(),
    })  # fmt: skip


def _bearbeiten(request, modell, form_klasse, pk, name):
    obj = get_object_or_404(modell, pk=pk) if pk else modell()
    form = form_klasse(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(request, f"{name} „{obj}“ gespeichert.")
        return redirect("links:liste")
    return render(request, "links/bearbeiten.html",
                  {"form": form, "obj": obj if pk else None, "name": name})  # fmt: skip


@never_cache
@pflegen
def link(request, pk=None):
    return _bearbeiten(request, Link, LinkForm, pk, "Link")


@never_cache
@pflegen
def gruppe(request, pk=None):
    return _bearbeiten(request, LinkGruppe, GruppeForm, pk, "Gruppe")


@require_POST
@pflegen
def loeschen(request, art, pk):
    modell = Link if art == "link" else LinkGruppe
    obj = get_object_or_404(modell, pk=pk)
    papierkorb.loeschen(request.user, str(modell._meta.verbose_name), str(obj), obj,
                        recht="einstellungen.links")  # fmt: skip
    messages.success(request, f"„{obj}“ in den Papierkorb gelegt.")
    return redirect("links:liste")
