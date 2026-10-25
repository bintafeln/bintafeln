"""Datensicherung in der Oberfläche: Export und Zurücklesen (ADR 0037)."""

import datetime as dt
import json
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from apps.core import datensicherung as ds
from apps.core import geheimnis, sicherung
from apps.konten import rollen
from apps.konten.views import nicht_in_demo

SITZUNG = "datenimport"
GUELTIG = dt.timedelta(hours=1)
MAX_SICHERUNGSALTER = dt.timedelta(hours=24)


def _ordner() -> Path:
    return Path(settings.MEDIA_ROOT) / "privat" / "datenimport"


def _alte_loeschen() -> None:
    grenze = (timezone.now() - GUELTIG).timestamp()
    if _ordner().is_dir():
        for datei in _ordner().iterdir():
            if datei.stat().st_mtime < grenze:
                datei.unlink(missing_ok=True)


def _laden(request) -> dict | None:
    name = request.session.get(SITZUNG, "")
    datei = _ordner() / f"{name}.bin"
    if not name or not datei.is_file():
        return None
    roh = geheimnis.bytes_entschluesseln(datei.read_bytes())
    return json.loads(roh) if roh else None


def _sicherung_frisch() -> bool:
    letzte = sicherung.lese_status().letzte_erfolgreiche
    return letzte is not None and timezone.now() - letzte <= MAX_SICHERUNGSALTER


@never_cache
@rollen.recht_erforderlich("daten.exportieren", "daten.importieren")
def seite(request):
    _alte_loeschen()
    return render(request, "core/datensicherung.html", {
        "bereiche": ds.BEREICHE, "min_passwort": ds.MIN_PASSWORT,
        "offen": bool(request.session.get(SITZUNG)) and _laden(request) is not None,
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("daten.exportieren")
@sensitive_post_parameters("passwort", "passwort2")
def exportieren(request):
    passwort = request.POST.get("passwort", "")
    if passwort != request.POST.get("passwort2", ""):
        messages.error(request, "Die beiden Passwörter stimmen nicht überein.")
        return redirect("core:datensicherung")
    try:
        inhalt = ds.exportieren(
            request.POST.getlist("bereiche"), passwort, request.user.get_username()
        )
    except ds.DatensicherungsFehler as fehler:
        messages.error(request, str(fehler))
        return redirect("core:datensicherung")
    antwort = HttpResponse(inhalt, content_type="application/octet-stream")
    name = f"bintafeln-export-{timezone.localtime():%Y-%m-%d_%H%M}.bintafeln"
    antwort["Content-Disposition"] = f'attachment; filename="{name}"'
    return antwort


@require_POST
@rollen.recht_erforderlich("daten.importieren")
@nicht_in_demo
@sensitive_post_parameters("passwort")
def pruefen(request):
    datei = request.FILES.get("datei")
    if datei is None:
        messages.error(request, "Bitte eine Exportdatei wählen.")
        return redirect("core:datensicherung")
    try:
        inhalt = ds.lesen(datei.read(), request.POST.get("passwort", ""))
    except ds.DatensicherungsFehler as fehler:
        messages.error(request, str(fehler))
        return redirect("core:datensicherung")
    # Bis zur Bestätigung verschlüsselt mit dem Schlüssel des Servers ablegen (höchstens 1 Stunde)
    name = uuid.uuid4().hex
    _ordner().mkdir(parents=True, exist_ok=True)
    roh = json.dumps(inhalt, ensure_ascii=False).encode()
    (_ordner() / f"{name}.bin").write_bytes(geheimnis.bytes_verschluesseln(roh))
    request.session[SITZUNG] = name
    return redirect("core:daten_vorschau")


@never_cache
@rollen.recht_erforderlich("daten.importieren")
def vorschau(request):
    inhalt = _laden(request)
    if inhalt is None:
        messages.error(request, "Keine geprüfte Datei vorhanden (oder älter als eine Stunde).")
        return redirect("core:datensicherung")
    return render(request, "core/datensicherung_vorschau.html", {
        "v": ds.vorschau(inhalt), "sicherung_frisch": _sicherung_frisch(),
    })  # fmt: skip


@require_POST
@rollen.recht_erforderlich("daten.importieren")
@nicht_in_demo
def uebernehmen(request):
    inhalt = _laden(request)
    if inhalt is None:
        messages.error(request, "Keine geprüfte Datei vorhanden (oder älter als eine Stunde).")
        return redirect("core:datensicherung")
    ersetzen = request.POST.get("modus") == "ersetzen"
    if ersetzen:
        if not _sicherung_frisch():
            messages.error(request, "Vor dem Ersetzen muss eine Server-Sicherung von heute "
                                    "vorliegen („./betrieb sichern“).")  # fmt: skip
            return redirect("core:daten_vorschau")
        if request.POST.get("bestaetigt") != "ja":
            messages.error(request, "Bitte das Ersetzen ausdrücklich bestätigen.")
            return redirect("core:daten_vorschau")
    try:
        gezaehlt = ds.zuruecklesen(inhalt, ersetzen=ersetzen)
    except ds.DatensicherungsFehler as fehler:
        messages.error(request, str(fehler))
        return redirect("core:daten_vorschau")
    _verwerfen(request)
    teile = ", ".join(f"{name}: {anzahl}" for name, anzahl in gezaehlt.items())
    art = "ersetzt" if ersetzen else "eingelesen (nichts gelöscht)"
    messages.success(request, f"Daten {art}. {teile or 'Keine Datensätze.'}")
    return redirect("core:start" if ersetzen else "core:datensicherung")


def _verwerfen(request) -> None:
    name = request.session.pop(SITZUNG, "")
    if name:
        (_ordner() / f"{name}.bin").unlink(missing_ok=True)


@require_POST
@rollen.recht_erforderlich("daten.importieren")
def verwerfen(request):
    _verwerfen(request)
    messages.success(request, "Die geprüfte Datei wurde verworfen.")
    return redirect("core:datensicherung")
