from auditlog.models import LogEntry
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from apps.core import geheimnis, mail, module, papierkorb, sicherung, update
from apps.core.forms import EinrichtungForm, EinstellungenForm, MailEinstellungenForm
from apps.core.middleware import admin_existiert
from apps.core.models import Hintergrundbild, MailEinstellungen, TafelEinstellungen
from apps.konten import personal, rollen
from apps.konten.views import nicht_in_demo


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")


@login_required
def start(request):
    from apps.antraege.models import Antrag
    from apps.antraege.models import fristen_anwenden as antragsfristen_anwenden
    from apps.ausgabe import korrekturen, sonderaktionen
    from apps.ausgabe.konto import buchungsfristen_anwenden
    from apps.ausgabe.models import Korrekturwunsch
    from apps.kunden.models import ImportVorbereitung, fristen_anwenden

    # Geprüfte, nicht übernommene Importe werden spätestens hier nach einer Stunde gelöscht;
    # Abholungen, Ausnahmen, Zugriffsprotokoll und Buchungen nach ihren Fristen.
    ImportVorbereitung.abgelaufene_loeschen()
    fristen_anwenden()
    buchungsfristen_anwenden()
    sonderaktionen.fristen_anwenden()
    korrekturen.fristen_anwenden()
    personal.stammdaten_leeren()
    antragsfristen_anwenden()
    module.fristen_anwenden()
    papierkorb.fristen_anwenden()
    kontext = {}
    if rollen.hat_recht(request.user, "antraege.sehen"):
        kontext["neue_antraege"] = Antrag.objects.filter(
            status=Antrag.Status.NEU, papierkorb_am__isnull=True
        ).count()
    if rollen.darf_mitarbeitende_verwalten(request.user):
        kontext["faellig"] = len(personal.faelligkeiten())
    if rollen.hat_recht(request.user, "korrekturen.entscheiden"):
        kontext["korrekturen_offen"] = Korrekturwunsch.objects.filter(
            status=Korrekturwunsch.Status.OFFEN
        ).count()
    if rollen.hat_recht(request.user, "kunden.nachrichten"):
        from apps.kunden.views_nachrichten import offene_je_anliegen

        kontext["nachrichten_offen"] = offene_je_anliegen()
        kontext["darf_verlaengern"] = rollen.hat_recht(request.user, "kunden.bearbeiten")
    if rollen.hat_recht(request.user, "einlass.nutzen"):
        from apps.ausgabe.stelle import aktuelle
        from apps.kunden import an_stelle

        kontext["notizen_an_stelle"] = list(an_stelle.offene(aktuelle(request.user)))
    if rollen.hat_recht(request.user, "system.status"):
        kontext["sicherung"] = sicherung.lese_status()
        kontext["sicherungsfehler"] = sicherung.auftraege_mit_fehler()
    # Update-Warnung (ADR 0084); die Mail zum Sicherheitsupdate geht bei jedem Besuch hier raus,
    # auch wenn niemand mit Update-Recht vorbeischaut
    warnung = update.warnung(update.stand())
    update.sicherheit_melden(warnung)
    if warnung and rollen.hat_recht(request.user, "system.update"):
        bis = TafelEinstellungen.laden().update_hinweis_bis
        if warnung.art != "neu" or not bis or bis < timezone.localdate():
            kontext["update_warnung"] = warnung
    kontext["modul_startseite"] = module.startseite(request)
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


@rollen.recht_erforderlich("einstellungen.tafel")
def einstellungen(request):
    instanz = TafelEinstellungen.laden()
    form = EinstellungenForm(request.POST or None, request.FILES or None, instance=instanz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("core:einstellungen")
    weitere = list(Hintergrundbild.objects.all())
    return render(request, "core/einstellungen.html", {"form": form, "weitere_bilder": weitere})


@require_POST
@rollen.recht_erforderlich("einstellungen.tafel")
def hintergrund_entfernen(request, pk):
    """Ein weiteres Hintergrundbild in den Papierkorb (ADR 0073)."""
    bild = get_object_or_404(Hintergrundbild, pk=pk)
    papierkorb.loeschen(request.user, "Hintergrundbild", str(bild), bild,
                        recht="einstellungen.tafel")  # fmt: skip
    messages.success(request, "Hintergrundbild entfernt (liegt im Papierkorb).")
    return redirect("core:einstellungen")


@never_cache
@rollen.recht_erforderlich("einstellungen.mail")
@nicht_in_demo
@sensitive_post_parameters("passwort")
def mail_einstellungen(request):
    instanz = MailEinstellungen.laden()
    form = MailEinstellungenForm(request.POST or None, instance=instanz)
    if request.method == "POST" and "pruefen" in request.POST:
        try:
            mail.verbindung_pruefen()
        except mail.MailFehler as fehler:
            messages.error(request, f"Verbindung fehlgeschlagen: {fehler}")
        else:
            messages.success(request, "Verbindung und Anmeldung am Mailserver klappen.")
        return redirect("core:mail_einstellungen")
    if request.method == "POST" and "testmail" in request.POST:
        an = request.POST.get("an", "").strip() or request.user.email
        try:
            validate_email(an)
        except ValidationError:
            messages.error(request, "Bitte eine gültige Empfängeradresse für die Testmail angeben.")
            return redirect("core:mail_einstellungen")
        try:
            mail.senden(
                "Testmail von bintafeln",
                "Diese Mail zeigt: bintafeln kann über den eingerichteten Mailserver senden.",
                [an],
            )
        except mail.MailFehler as fehler:
            messages.error(request, f"Testmail nicht gesendet: {fehler}")
        else:
            messages.success(
                request, f"Testmail an {an} gesendet. Bitte im Postfach (auch im Spam) nachsehen."
            )
        return redirect("core:mail_einstellungen")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "E-Mail-Einstellungen gespeichert.")
        return redirect("core:mail_einstellungen")
    lesbar = geheimnis.entschluesseln(instanz.passwort_verschluesselt)
    return render(
        request,
        "core/mail_einstellungen.html",
        {
            "form": form,
            "einstellungen": instanz,
            "passwort_gespeichert": bool(instanz.passwort_verschluesselt),
            "passwort_unlesbar": lesbar is None,
        },
    )


@rollen.recht_erforderlich("protokoll.sehen")
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


@login_required
def hilfe(request):
    """Handbuch: nur die Kapitel, die zu den Rechten des Kontos passen (ADR 0038)."""
    from apps.core import hilfe as handbuch

    kapitel = handbuch.sichtbar(request.user)
    return render(
        request,
        "hilfe/handbuch.html",
        {"kapitel": kapitel, "teile": handbuch.gegliedert(kapitel)},
    )


@never_cache
@login_required
def suche(request):
    """Suche im Seitenkopf (ADR 0040): ganze Seite, mit HTMX nur die Liste unter dem Feld."""
    from apps.core import suche as such
    from apps.core.menue import menue

    eingabe = request.GET.get("q", "")[:200]
    if request.GET.get("nur") == "hilfe" and such.zerlegen(eingabe)[0] is None:
        eingabe = f"h {eingabe}"  # Suchfeld im Handbuch
    # Kurze Liste unter einem Suchfeld (Seitenkopf, Handbuch); das Tippen auf der Suchseite selbst
    # holt die ganze Seite (live_suche), springt dabei aber nicht zum Kunden
    kurz = request.headers.get("HX-Target") in ("kopf-suche-liste", "handbuch-suche-liste")
    if not request.headers.get("HX-Request") and (ziel := such.direkt(request.user, eingabe)):
        return redirect(ziel)  # Enter mit genauer Kundennummer: gleich zum Kunden
    ergebnis = such.suchen(
        request.user,
        eingabe,
        grenze=such.JE_BEREICH if kurz else such.JE_BEREICH_SEITE,
        menue=menue(request),
    )
    kontext = {"e": ergebnis, "kuerzel": such.kuerzel_fuer(request.user),
               "mindestlaenge": such.MINDESTLAENGE}  # fmt: skip
    vorlage = "core/_suche.html" if kurz else "core/suche.html"
    return render(request, vorlage, kontext)
