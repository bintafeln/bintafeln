"""Produktivstart in der Oberfläche: einmalig alle Testdaten löschen (ADR 0095).

Erst wird eine verschlüsselte Komplett-Sicherung erzeugt und heruntergeladen, dann wird
gelöscht. Nur mit dem Recht ``system.produktivstart`` (hat nur der Admin) und im Demo gesperrt.
"""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from apps.core import datensicherung as ds
from apps.core import produktivstart as ps
from apps.konten import rollen
from apps.konten.views import nicht_in_demo

BESTAETIGUNG = "PRODUKTIVSTART"


@rollen.recht_erforderlich("system.produktivstart")
def seite(request):
    return render(request, "core/produktivstart.html", {
        "bereiche": ps.vorschau(request.user),
        "min_passwort": ds.MIN_PASSWORT,
        "wort": BESTAETIGUNG,
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("system.produktivstart")
@nicht_in_demo
@sensitive_post_parameters("passwort", "passwort2")
def ausfuehren(request):
    if request.POST.get("bestaetigung", "").strip() != BESTAETIGUNG:
        messages.error(request, f"Bitte zur Bestätigung „{BESTAETIGUNG}“ eingeben.")
        return redirect("core:produktivstart")
    passwort = request.POST.get("passwort", "")
    if passwort != request.POST.get("passwort2", ""):
        messages.error(request, "Die beiden Passwörter stimmen nicht überein.")
        return redirect("core:produktivstart")
    if len(passwort) < ds.MIN_PASSWORT:
        messages.error(
            request, f"Das Sicherungs-Passwort braucht mindestens {ds.MIN_PASSWORT} Zeichen."
        )
        return redirect("core:produktivstart")
    gewaehlt = set(request.POST.getlist("bereiche"))
    if not gewaehlt:
        messages.error(request, "Bitte mindestens einen Bereich zum Löschen auswählen.")
        return redirect("core:produktivstart")
    # Erst sichern (immer alles), dann löschen – schlägt die Sicherung fehl, bleibt alles stehen.
    try:
        inhalt = ds.exportieren(list(ds.BEREICHE), passwort, request.user.get_username())
    except ds.DatensicherungsFehler as fehler:
        messages.error(request, f"Sicherung fehlgeschlagen, es wurde nichts gelöscht: {fehler}")
        return redirect("core:produktivstart")
    try:
        ps.durchfuehren(request.user, gewaehlt)
    except ps.ProduktivstartFehler as fehler:
        messages.error(request, f"Produktivstart abgebrochen, es wurde nichts gelöscht: {fehler}")
        return redirect("core:produktivstart")
    antwort = HttpResponse(inhalt, content_type="application/octet-stream")
    name = f"bintafeln-vor-produktivstart-{timezone.localtime():%Y-%m-%d_%H%M}.bintafeln"
    antwort["Content-Disposition"] = f'attachment; filename="{name}"'
    return antwort
