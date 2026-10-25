"""Serienbriefe (ADR 0047): Vorlagen pflegen, Empfänger wählen, PDF oder E-Mails."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core import mail
from apps.core.models import TafelEinstellungen
from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.konten.views import nicht_in_demo
from apps.serienbriefe import empfaenger as emp
from apps.serienbriefe.brief import briefe_pdf
from apps.serienbriefe.forms import AuswahlForm, VorlageForm
from apps.serienbriefe.models import Versand, Vorlage


@rollen.recht_erforderlich("serienbriefe.erstellen")
def vorlagen(request):
    return render(request, "serienbriefe/vorlagen.html", {
        "vorlagen": Vorlage.objects.all(), "versaende": Versand.objects.all()[:30],
    })  # fmt: skip


@never_cache
@rollen.recht_erforderlich("serienbriefe.erstellen")
def vorlage(request, pk=None):
    v = get_object_or_404(Vorlage, pk=pk) if pk else Vorlage()
    form = VorlageForm(request.POST or None, instance=v)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Vorlage „{v.name}“ gespeichert.")
        return redirect("serienbriefe:vorlagen")
    return render(request, "serienbriefe/vorlage.html", {
        "form": form, "v": v, "platzhalter": emp.PLATZHALTER,
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("serienbriefe.erstellen")
def vorlage_loeschen(request, pk):
    v = get_object_or_404(Vorlage, pk=pk)
    v.delete()
    messages.success(request, f"Vorlage „{v.name}“ gelöscht.")
    return redirect("serienbriefe:vorlagen")


def _allgemein(jahr: int) -> dict:
    """Alle bekannten Platzhalter (leer, wo sie für den Empfänger nicht passen)."""
    werte = {name: "" for name, _ in emp.PLATZHALTER}
    werte |= {"jahr": jahr, "datum": f"{timezone.localdate():%d.%m.%Y}",
              "tafel": TafelEinstellungen.laden().name}  # fmt: skip
    return werte


def _beschreibung(d: dict) -> str:
    teile = [dict(emp.QUELLEN)[d["quelle"]]]
    if d["quelle"] == "adressen" and d.get("kategorien"):
        teile.append(", ".join(k.name for k in d["kategorien"]))
    if d["quelle"] in ("spender",) or d.get("nur_offen"):
        teile.append(str(d["jahr"]))
    if d.get("nur_offen"):
        teile.append("offener Beitrag")
    return " · ".join(teile)[:300]


@never_cache
@rollen.recht_erforderlich("serienbriefe.erstellen")
def erstellen(request):
    form = AuswahlForm(request.POST or None, benutzer=request.user,
                       initial={"vorlage": request.GET.get("vorlage")})  # fmt: skip
    kontext = {"form": form}
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        alle = emp.suchen(d["quelle"], d, request.user)
        erreichbar, ohne = emp.aufteilen(alle, d["versandart"])
        allgemein = _allgemein(d["jahr"])
        v = d["vorlage"]
        schritt = request.POST.get("schritt", "vorschau")
        if schritt == "pdf" and erreichbar:
            inhalt = briefe_pdf(
                [
                    (
                        e.anschrift,
                        emp.einsetzen(v.betreff, e, allgemein),
                        emp.einsetzen(v.text, e, allgemein),
                    )
                    for e in erreichbar
                ]
            )
            Versand.objects.create(von=request.user.get_username(), art=Versand.Art.BRIEF,
                                   vorlage=v.name, betreff=v.betreff, auswahl=_beschreibung(d),
                                   anzahl=len(erreichbar),
                                   empfaenger=[e.schluessel for e in erreichbar])  # fmt: skip
            return pdf_antwort(inhalt, f"serienbrief-{timezone.localdate():%Y-%m-%d}.pdf")
        if schritt == "senden" and erreichbar:
            return _senden(request, v, d, erreichbar, allgemein)
        kontext |= {
            "erreichbar": erreichbar, "ohne": ohne, "d": d,
            "beispiel": erreichbar[0] if erreichbar else None,
            "beispiel_betreff": emp.einsetzen(v.betreff, erreichbar[0], allgemein)
            if erreichbar else "",
            "beispiel_text": emp.einsetzen(v.text, erreichbar[0], allgemein) if erreichbar else "",
            "mail_bereit": mail.eingerichtet(),
        }  # fmt: skip
    return render(request, "serienbriefe/erstellen.html", kontext)


@nicht_in_demo
def _senden(request, v, d, erreichbar, allgemein):
    """Jede Mail einzeln (keine fremden Adressen im Verteiler)."""
    gesendet, fehler = [], []
    for e in erreichbar:
        try:
            mail.senden(emp.einsetzen(v.betreff, e, allgemein),
                        emp.einsetzen(v.text, e, allgemein), [e.email])  # fmt: skip
        except mail.MailFehler as grund:
            fehler.append(f"{e.name}: {grund}")
            if len(fehler) >= 3 and not gesendet:
                break  # Mailserver geht offenbar gar nicht
        else:
            gesendet.append(e)
    if gesendet:
        Versand.objects.create(von=request.user.get_username(), art=Versand.Art.EMAIL,
                               vorlage=v.name, betreff=v.betreff, auswahl=_beschreibung(d),
                               anzahl=len(gesendet),
                               empfaenger=[e.schluessel for e in gesendet])  # fmt: skip
        messages.success(request, f"{len(gesendet)} E-Mail{'s' if len(gesendet) != 1 else ''} "
                                  "gesendet.")  # fmt: skip
    for f in fehler[:10]:
        messages.error(request, f"Nicht gesendet: {f}")
    return redirect("serienbriefe:vorlagen")
