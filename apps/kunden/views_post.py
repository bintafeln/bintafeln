"""Post der Verwaltung an die Ausgabestellen (ADR 0142): schreiben, Postfach, Eule in der
Kopfzeile."""

from urllib.parse import urlsplit

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core.forms import Mehrfachauswahl
from apps.konten import rollen
from apps.kunden import eulenpost
from apps.kunden.models import Ausgabestelle, PostEmpfang, Rundschreiben


def _stelle(request):
    from apps.ausgabe.stelle import aktuelle

    return aktuelle(request.user)


class PostForm(forms.Form):
    stellen = forms.ModelMultipleChoiceField(
        Ausgabestelle.objects.none(), required=False, label="An",
        widget=Mehrfachauswahl(leer="alle Ausgabestellen"),
        help_text="Nichts angehakt = an alle Ausgabestellen.")  # fmt: skip
    betreff = forms.CharField(label="Betreff", max_length=200)
    text = forms.CharField(label="Nachricht", max_length=4000,
                           widget=forms.Textarea(attrs={"rows": 6}))  # fmt: skip
    wichtig = forms.BooleanField(
        label="Wichtig", required=False,
        help_text="Legt bei der Ausgabestelle zusätzlich einen Hinweis über die Seite, bis jemand "
        "ihn als gelesen bestätigt.")  # fmt: skip

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stellen"].queryset = eulenpost.waehlbare_stellen()


@never_cache
@rollen.recht_erforderlich("kunden.nachrichten")
def schreiben(request):
    form = PostForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stellen = list(form.cleaned_data["stellen"]) or list(eulenpost.waehlbare_stellen())
        if not stellen:
            form.add_error("stellen", "Es gibt keine aktive Ausgabestelle.")
        else:
            daten = form.cleaned_data
            eulenpost.schreiben(stellen, request.user, daten["betreff"], daten["text"],
                                daten["wichtig"])  # fmt: skip
            namen = ", ".join(s.name for s in stellen)
            messages.success(request, f"Die Eule ist unterwegs zu: {namen}.")
            return redirect("kunden:post_schreiben")
    return render(request, "kunden/post_schreiben.html",
                  {"form": form, "gesendet": eulenpost.gesendet()})  # fmt: skip


@require_POST
@rollen.recht_erforderlich("kunden.nachrichten")
def loeschen(request, pk):
    rundschreiben = get_object_or_404(Rundschreiben, pk=pk)
    eulenpost.loeschen(rundschreiben, request.user)
    messages.success(request, f"„{rundschreiben.betreff}“ gelöscht – bei allen Ausgabestellen. "
                     "Im Papierkorb lässt sie sich wiederherstellen.")  # fmt: skip
    return redirect("kunden:post_schreiben")


@never_cache
@rollen.recht_erforderlich("einlass.nutzen")
def postfach(request):
    stelle = _stelle(request)
    return render(request, "kunden/postfach.html",
                  {"stelle": stelle, "post": eulenpost.postfach(stelle)})  # fmt: skip


@never_cache
@rollen.recht_erforderlich("einlass.nutzen")
def kopf(request):
    """Die Eule in der Kopfzeile frisch (HTMX, jede Minute).

    „Gelesen“ im Hinweis führt zurück auf die Seite, auf der man gerade ist – nicht auf diese
    Adresse, die nur das Stück Kopfzeile liefert (das gäbe eine fast leere, weiße Seite).
    """
    return render(request, "kunden/_eulenpost.html", {
        "eulenpost": eulenpost.stand(_stelle(request)),
        "eulen_zurueck": request.headers.get("HX-Current-URL", "") or reverse("kunden:postfach"),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("einlass.nutzen")
def gelesen(request, pk):
    stelle = _stelle(request)
    empfang = get_object_or_404(PostEmpfang.objects.filter(stelle=stelle), pk=pk)
    eulenpost.gelesen(empfang, request.user)
    if request.headers.get("HX-Request"):
        return render(request, "kunden/_eulenpost.html", {"eulenpost": eulenpost.stand(stelle)})
    zurueck = request.POST.get("zurueck", "")
    if not url_has_allowed_host_and_scheme(zurueck, allowed_hosts={request.get_host()}) or urlsplit(
        zurueck
    ).path == reverse("kunden:post_kopf"):  # nur ein Stück Kopfzeile
        zurueck = "kunden:postfach"
    return redirect(zurueck)
