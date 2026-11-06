"""Anträge bearbeiten (Admin, Büro) und das Formular einstellen (Admin)."""

import csv
import io
import logging
from types import SimpleNamespace

from auditlog.signals import accessed
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.antraege import auskunft, ausweis_pruefung, ausweis_scan, gebiet, sprachen
from apps.antraege import uebersetzen as uebersetzen_ki
from apps.antraege.forms import (
    AntragBearbeitenForm,
    AntragPersonenFormset,
    EinstellungenForm,
    TextForm,
)
from apps.antraege.models import (
    ANHANG_ORDNER,
    Antrag,
    AntragAnhang,
    AntragAnmerkung,
    AntragEinstellungen,
    AntragText,
    in_papierkorb,
)
from apps.core import html, listenauswahl, listenexport, privatdateien
from apps.core.pdf import pdf_antwort
from apps.konten import rollen

log = logging.getLogger(__name__)

ANSICHTEN = {
    "offen": ("Offen", Q(status__in=Antrag.OFFEN)),
}
# Spalte in der Adresse → Sortierfeld; Standard: neueste zuerst
SORTIERUNG = {
    "nummer": "laufnummer", "status": "status", "kundennummer": "kundennummer",
    "nachname": "nachname", "vorname": "vorname", "eingang": "eingegangen_am", "email": "email",
    "telefon": "telefon", "art": "art", "staat": "staatsangehoerigkeit",
}  # fmt: skip
ZEILEN = ["25", "50", "100", "alle"]

# Spalten der Antragsliste; „nummer" (die Antragsnummer mit Link) ist immer sichtbar, die übrigen
# wählt jede Person selbst (Benutzer.antraege_liste_aus).
SPALTEN = [("nummer", "#"), ("status", "Status"), ("kundennummer", "Kundennummer"),
           ("nachname", "Nachname"), ("vorname", "Vorname"), ("eingang", "Antrag vom"),
           ("email", "E-Mail"), ("telefon", "Telefon"), ("art", "Art"),
           ("staat", "Staatsangehörigkeit")]  # fmt: skip
SPALTEN_FEST = {"nummer"}


def _gefiltert(request):
    ansicht = request.GET.get("ansicht", "offen")
    if ansicht not in ANSICHTEN:
        ansicht = "offen"
    antraege = Antrag.objects.filter(ANSICHTEN[ansicht][1])
    suche = request.GET.get("suche", "").strip()
    for wort in suche.split():
        teile = Q(vorname__icontains=wort) | Q(nachname__icontains=wort)
        teile |= Q(kundennummer__iexact=wort) | Q(email__icontains=wort)
        teile |= Q(telefon__icontains=wort) | Q(staatsangehoerigkeit__icontains=wort)
        if wort.isdigit():
            teile |= Q(laufnummer=int(wort))
        antraege = antraege.filter(teile)
    return ansicht, suche, antraege


def _sortiert(request, antraege):
    sort = request.GET.get("sort", "-nummer")
    feld = SORTIERUNG.get(sort.lstrip("-"))
    if not feld:
        sort, feld = "-nummer", "laufnummer"
    return sort, antraege.order_by(("-" if sort.startswith("-") else "") + feld, "-pk")


@rollen.recht_erforderlich("antraege.sehen")
def liste(request):
    ansicht, suche, antraege = _gefiltert(request)
    sort, antraege = _sortiert(request, antraege)
    zeilen = request.GET.get("zeilen", "25")
    if zeilen not in ZEILEN:
        zeilen = "25"
    letzte = AntragAnmerkung.objects.filter(antrag=OuterRef("pk")).order_by("-zeitpunkt")
    antraege = antraege.annotate(kommentar=Subquery(letzte.values("text")[:1]))
    seite = Paginator(antraege, 10**9 if zeilen == "alle" else int(zeilen)).get_page(
        request.GET.get("seite")
    )
    e = AntragEinstellungen.laden()
    for a in seite:
        a.ausserhalb = gebiet.ausserhalb(e, a)
    aus = set(request.user.antraege_liste_aus or [])
    sichtbar = {k for k, _ in SPALTEN if k in SPALTEN_FEST or k not in aus}
    spalten = [(k, titel) for k, titel in SPALTEN if k in sichtbar]
    spalten_wahl = [(k, titel, k not in aus) for k, titel in SPALTEN if k not in SPALTEN_FEST]
    ausweis_scan.fortsetzen_wenn_unterbrochen()  # durch ein Update abgebrochenen Lauf fortsetzen
    return render(
        request,
        "antraege/liste.html",
        {
            "seite": seite,
            "ansicht": ansicht,
            "ansichten": [(k, name) for k, (name, _) in ANSICHTEN.items()],
            "suche": suche,
            "sort": sort,
            "zeilen": zeilen,
            "zeilen_auswahl": ZEILEN,
            "spalten": spalten,
            "sichtbar": sichtbar,
            "spalten_wahl": spalten_wahl,
            "abfrage": request.GET.urlencode(),
            "offen_gesamt": Antrag.objects.filter(ANSICHTEN["offen"][1]).count(),
            "ausweis_pruefen": ausweis_pruefung.aktiv(e),
            "ausweis_lauf": ausweis_scan.fortschritt(),
        },
    )


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def spalten(request):
    """Eigene Auswahl der Spalten in der Antragsliste (am Konto gespeichert)."""
    from django.http import QueryDict

    gewaehlt = set(request.POST.getlist("spalte"))
    request.user.antraege_liste_aus = [k for k, _ in SPALTEN
                                       if k not in SPALTEN_FEST and k not in gewaehlt]  # fmt: skip
    request.user.save(update_fields=["antraege_liste_aus"])
    zurueck = QueryDict(request.POST.get("zurueck", "")).urlencode()
    return redirect(f"{reverse('antraege:liste')}?{zurueck}" if zurueck else "antraege:liste")


@rollen.recht_erforderlich("antraege.bearbeiten")
def bearbeiten(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    form = AntragBearbeitenForm(request.POST or None, instance=a)
    personen = AntragPersonenFormset(request.POST or None, instance=a, prefix="p")
    if request.method == "POST" and form.is_valid() and personen.is_valid():
        with transaction.atomic():
            a = form.save(commit=False)
            a.bearbeitet_von = request.user.get_username()
            a.save()
            personen.save()
        messages.success(request, f"Antrag {a.nummer} gespeichert.")
        return redirect("antraege:antrag", pk=a.pk)
    return render(request, "antraege/bearbeiten.html", {"a": a, "form": form, "personen": personen})


@rollen.recht_erforderlich("antraege.sehen")
def antrag(request, pk):
    from apps.antraege import ausweis_pruefung

    a = get_object_or_404(Antrag, pk=pk)
    accessed.send(sender=Antrag, instance=a)  # Aufruf im Änderungsprotokoll
    davor = Antrag.objects.filter(ANSICHTEN["offen"][1], eingegangen_am__lt=a.eingegangen_am)
    e = AntragEinstellungen.laden()
    # Zum Durchblättern: voriger/nächster Antrag nach Antragsnummer (über alle Anträge).
    voriger = naechster = None
    if a.laufnummer is not None:
        voriger = (Antrag.objects.filter(laufnummer__lt=a.laufnummer)
                   .order_by("-laufnummer").first())  # fmt: skip
        naechster = (Antrag.objects.filter(laufnummer__gt=a.laufnummer)
                     .order_by("laufnummer").first())  # fmt: skip
    kontext = {
        "a": a,
        "sprache": sprachen.sprache(a.sprache),
        "platz": davor.count() + 1 if a.status in Antrag.OFFEN else None,
        "ausserhalb": gebiet.ausserhalb(e, a),
        "status_auswahl": Antrag.Status.choices,
        "ausweis_pruefen": ausweis_pruefung.aktiv(e),
        "voriger": voriger,
        "naechster": naechster,
    }
    # Hinweis-Banner bei einer erkannten Abweichung der Staatsangehörigkeit (ADR 0107): Bild zeigen
    # und (mit Bearbeiten-Recht) die Übernahme anbieten.
    darf = rollen.hat_recht(request.user, "antraege.bearbeiten")
    if a.ausweis_abweichung and a.ausweis_staat and darf:
        from apps.core import auswahl

        bekannt = a.ausweis_staat in auswahl.LAENDERCODE
        staaten = auswahl.mit_vorhandenem(auswahl.staatsangehoerigkeiten(), a.staatsangehoerigkeit)
        kontext["ausweis_staaten"] = (
            auswahl.mit_vorhandenem(staaten, a.ausweis_staat) if bekannt else staaten
        )
        kontext["ausweis_vorschlag"] = a.ausweis_staat if bekannt else a.staatsangehoerigkeit
    return render(request, "antraege/antrag.html", kontext)


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def status(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    neu = request.POST.get("status")
    if neu in Antrag.Status.values:
        a.status_setzen(neu, request.user.get_username())
        messages.success(request, f"Status: {a.get_status_display()}.")
    return redirect("antraege:antrag", pk=a.pk)


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def anmerkung(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    text = request.POST.get("text", "").strip()
    if text:
        AntragAnmerkung.objects.create(antrag=a, text=text, von=request.user.get_username())
        messages.success(request, "Anmerkung gespeichert.")
    return redirect("antraege:antrag", pk=a.pk)


@require_POST
@rollen.recht_erforderlich("antraege.loeschen")
def papierkorb(request, pk):
    """Legt den Antrag in den gemeinsamen Papierkorb (ADR 0073): von dort wiederherstellbar,
    danach endgültig gelöscht nach der Tafel-weiten Frist."""
    a = get_object_or_404(Antrag, pk=pk)
    nummer = a.nummer
    in_papierkorb(a, request.user)
    messages.success(request, f"Antrag {nummer} in den Papierkorb gelegt.")
    return redirect("antraege:liste")


@never_cache
@rollen.recht_erforderlich("antraege.sehen")
def anhang(request, pk, anhang):
    d = get_object_or_404(AntragAnhang, pk=anhang, antrag_id=pk)
    inhalt = privatdateien.lesen(ANHANG_ORDNER, d.datei)
    if inhalt is None:
        raise Http404
    accessed.send(sender=AntragAnhang, instance=d)
    antwort = HttpResponse(inhalt, content_type=d.typ)
    antwort["Content-Disposition"] = "inline"
    return antwort


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def nachweis_hinzufuegen(request, pk):
    """Nachträglich Nachweise zu einem Antrag hochladen (verschlüsselt, ADR 0105)."""
    from apps.antraege import nachweise

    a = get_object_or_404(Antrag, pk=pk)
    dateien = request.FILES.getlist("dateien")
    if not dateien:
        messages.error(request, "Bitte mindestens eine Datei auswählen.")
        return redirect("antraege:antrag", pk=a.pk)
    vorher = a.anhaenge.count()
    for meldung in nachweise.anhang_hinzufuegen(a, dateien):
        messages.error(request, meldung)
    neu = a.anhaenge.count() - vorher
    if neu == 1:
        messages.success(request, "Ein Nachweis hinzugefügt.")
    elif neu > 1:
        messages.success(request, f"{neu} Nachweise hinzugefügt.")
    return redirect("antraege:antrag", pk=a.pk)


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def nachweis_entfernen(request, pk, anhang):
    """Einen Nachweis in den gemeinsamen Papierkorb legen (ADR 0073): wiederherstellbar, danach
    endgültig gelöscht nach der Tafel-weiten Frist."""
    from apps.core import papierkorb

    a = get_object_or_404(Antrag, pk=pk)
    d = get_object_or_404(AntragAnhang, pk=anhang, antrag=a)
    name = d.name
    papierkorb.loeschen(request.user, "Nachweis", f"{name} · Antrag {a.nummer}", d,
                        recht="antraege.bearbeiten", kundennummer=a.kundennummer)  # fmt: skip
    messages.success(request, f"Nachweis „{name}“ in den Papierkorb gelegt.")
    return redirect("antraege:antrag", pk=a.pk)


@require_POST
@rollen.recht_erforderlich("antraege.sehen")
def nachweis_pruefen(request, pk, anhang):
    """Liest lokal per OCR die MRZ eines Nachweis-Fotos und zeigt Land/Staatsangehörigkeit als
    Hinweis (ADR 0107). Nichts automatisch; jeder Aufruf wird protokolliert."""
    from apps.antraege import ausweis_pruefung

    a = get_object_or_404(Antrag, pk=pk)
    if not ausweis_pruefung.aktiv(AntragEinstellungen.laden()):
        raise Http404
    d = get_object_or_404(AntragAnhang, pk=anhang, antrag=a)
    inhalt = privatdateien.lesen(ANHANG_ORDNER, d.datei)
    if inhalt is None:
        raise Http404
    accessed.send(sender=AntragAnhang, instance=d)
    bericht = ausweis_pruefung.pruefen_datei(inhalt, d.typ, a.staatsangehoerigkeit)
    return render(request, "antraege/_ausweis_ergebnis.html", _ausweis_kontext(request, a, bericht))


@rollen.recht_erforderlich("antraege.sehen")
def nachweis_vorschau(request, pk, anhang):
    """Kleine Vorschau eines PDF-Nachweises (erste Seite, ADR 0107). Lokal gerendert; nicht
    serverseitig zwischengespeichert (der Nachweis liegt verschlüsselt)."""
    from apps.antraege import pdf_bilder

    a = get_object_or_404(Antrag, pk=pk)
    d = get_object_or_404(AntragAnhang, pk=anhang, antrag=a)
    if "pdf" not in (d.typ or "").lower():
        raise Http404
    inhalt = privatdateien.lesen(ANHANG_ORDNER, d.datei)
    bild = pdf_bilder.vorschau(inhalt) if inhalt else None
    if bild is None:
        raise Http404
    antwort = HttpResponse(bild, content_type="image/jpeg")
    antwort["Cache-Control"] = "private, max-age=600"  # nur im Browser des Mitarbeiters
    return antwort


def _ausweis_kontext(request, a, bericht):
    """Kontext für das Ergebnis der Ausweisprüfung: Bericht, Antrag und – wer bearbeiten darf –
    die Länderauswahl, um die Staatsangehörigkeit im Antrag zu überschreiben."""
    from apps.core import auswahl

    darf = rollen.hat_recht(request.user, "antraege.bearbeiten")
    kontext = {"b": bericht, "a": a, "darf_bearbeiten": darf}
    if darf and bericht.get("erkannt"):
        staaten = auswahl.mit_vorhandenem(auswahl.staatsangehoerigkeiten(), a.staatsangehoerigkeit)
        erkannt = bericht.get("staatsangehoerigkeit", "")
        bekannt = erkannt in auswahl.LAENDERCODE  # erkannter Name ist ein echtes Land
        # Den erkannten Namen wählbar machen und (wenn bekannt) vorschlagen, sonst die Antragsangabe
        kontext["staaten"] = auswahl.mit_vorhandenem(staaten, erkannt) if bekannt else staaten
        kontext["vorschlag"] = erkannt if bekannt else a.staatsangehoerigkeit
    return kontext


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def nachweis_staat_uebernehmen(request, pk):
    """Die (per Ausweisprüfung erkannte oder von Hand gewählte) Staatsangehörigkeit in den Antrag
    übernehmen (ADR 0107). Nur nach Klick; der Mensch entscheidet."""
    from apps.core import auswahl

    a = get_object_or_404(Antrag, pk=pk)
    wert = (request.POST.get("staatsangehoerigkeit") or "").strip()
    # Nur Werte aus der Länderliste (plus die bisherige Antragsangabe) zulassen – nicht den
    # eingesandten Wert selbst in die erlaubte Menge aufnehmen.
    auswahlliste = auswahl.mit_vorhandenem(auswahl.staatsangehoerigkeiten(), a.staatsangehoerigkeit)
    gespeichert = bool(wert) and wert in {w for w, _ in auswahlliste}
    if gespeichert:
        a.staatsangehoerigkeit = wert
        a.ausweis_abweichung = False  # vom Menschen geprüft und gesetzt → kein Hinweis mehr
        a.save(update_fields=["staatsangehoerigkeit", "ausweis_abweichung"])
        messages.success(request, f"Staatsangehörigkeit im Antrag auf „{wert}“ gesetzt.")
    return render(
        request, "antraege/_ausweis_uebernommen.html", {"wert": wert, "gespeichert": gespeichert}
    )


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def ausweise_pruefen_alle(request):
    """Auf Befehl alle Anträge im Hintergrund auf Ausweise prüfen (ADR 0107). Gibt eine ehrliche
    Rückmeldung: läuft schon, nichts zu tun (alles geprüft) oder jetzt für N Anträge gestartet –
    sonst stünde „läuft im Hintergrund“ da, obwohl gar kein Fortschritt kommt."""
    if not ausweis_scan.aktiv():
        messages.error(
            request, "Die Ausweisprüfung ist nicht eingeschaltet (Antragseinstellungen)."
        )
    elif ausweis_scan.laeuft_schon():
        messages.info(request, "Die Ausweisprüfung läuft bereits – der Fortschritt steht oben.")
    elif (offen := ausweis_scan.offene_anzahl()) == 0:
        messages.info(
            request,
            "Alle Anträge sind bereits geprüft – es gibt nichts Neues zu prüfen. Neue Anträge "
            "werden beim Eingang ohnehin automatisch geprüft.",
        )
    else:
        ausweis_scan.alle_pruefen_starten()
        messages.success(
            request,
            f"Ausweisprüfung für {offen} noch nicht geprüfte "
            f"{'Anträge' if offen != 1 else 'Antrag'} gestartet – der Fortschritt erscheint oben.",
        )
    return redirect("antraege:liste")


@rollen.recht_erforderlich("antraege.sehen")
def ausweis_fortschritt(request):
    """Stand der laufenden Sammelprüfung (htmx, lädt sich selbst nach, bis fertig)."""
    ausweis_scan.fortsetzen_wenn_unterbrochen()  # nach einem Update-Neustart selbst weiterlaufen
    stand = ausweis_scan.fortschritt()
    return render(request, "antraege/_ausweis_fortschritt.html", {"stand": stand})


@rollen.recht_erforderlich("antraege.bearbeiten")
def ausweis_pruefung_liste(request):
    """Sammel-Seite der Ausweisprüfung (ADR 0107/0112): offene Abweichungen zum Entscheiden, dazu
    die „nichts erkannt“-Fälle getrennt nach Amtsdokument (Bescheid – kann ignoriert werden) und
    unklar (evtl. unlesbarer Ausweis). Mit Mini-Vorschau und je Zeile den passenden Knöpfen –
    damit man nicht jeden Antrag einzeln öffnen muss."""

    def _laden(**filter):
        qs = (
            Antrag.objects.filter(ausweis_erledigt=False, **filter)
            .select_related("ausweis_anhang")
            .prefetch_related("personen")
            .order_by("eingegangen_am", "pk")
        )
        return [_ausweis_zeile(a) for a in qs]

    kontext = {
        "abweichungen": _laden(ausweis_befund="abweichung"),
        "unklar": _laden(ausweis_befund="unklar"),
        "amtsdokumente": _laden(ausweis_befund="amtsdokument"),
    }
    return render(request, "antraege/ausweis_pruefung.html", kontext)


def _ausweis_zeile(a) -> dict:
    """Eine Zeile der Sammel-Prüfseite aufbereiten (Vorschau-Angaben, angegeben/erkannt)."""
    from apps.core import auswahl

    anhang = a.ausweis_anhang
    typ = (anhang.typ or "").lower() if anhang else ""
    return {
        "a": a,
        "angegeben": ", ".join(sorted(_angegebene_namen(a))),
        "erkannt": a.ausweis_staat,
        # Übernehmen nur anbieten, wenn der erkannte Staat ein echtes Land aus der Liste ist.
        "uebernehmbar": a.ausweis_staat in auswahl.LAENDERCODE,
        "anhang_id": anhang.pk if anhang else None,
        "anhang_bild": "image" in typ,  # Foto → großes Popup; PDF → eigenes Fenster
        "anhang_pdf": "pdf" in typ,
        "hat_vorschau": "image" in typ or "pdf" in typ,
    }


def _angegebene_namen(a) -> set[str]:
    """Angegebene Staatsangehörigkeiten (Hauptperson + Angehörige), für die Anzeige."""
    namen = [a.staatsangehoerigkeit] + [p.staatsangehoerigkeit for p in a.personen.all()]
    return {n.strip() for n in namen if n and n.strip()}


@require_POST
@rollen.recht_erforderlich("antraege.bearbeiten")
def ausweis_entscheiden(request, pk):
    """Eine Abweichung auf der Sammel-Seite abschließen (htmx). ``aktion``:
    - ``uebernehmen``: erkannte Staatsangehörigkeit in den Antrag übernehmen,
    - ``verwerfen``: nicht übernehmen (Antrag bleibt), Hinweis erledigt,
    - ``amtsdokument``: den Fall von Hand als Bescheid (Amtsdokument) einordnen und abhaken.
    Alle entfernen die Zeile aus der offenen Liste. „Ansehen/Später" ist nur ein Link zum Antrag
    und braucht keine Aktion."""
    from apps.core import auswahl

    a = get_object_or_404(Antrag, pk=pk)
    aktion = request.POST.get("aktion")
    text = ""
    if aktion == "uebernehmen":
        wert = a.ausweis_staat
        erlaubt = {w for w, _ in auswahl.mit_vorhandenem(
            auswahl.staatsangehoerigkeiten(), a.staatsangehoerigkeit)}  # fmt: skip
        if wert and wert in erlaubt:
            a.staatsangehoerigkeit = wert
            a.ausweis_abweichung = False
            a.ausweis_erledigt = True
            a.save(update_fields=["staatsangehoerigkeit", "ausweis_abweichung", "ausweis_erledigt"])
            text = f"„{wert}“ übernommen."
        else:
            text = "Nicht übernehmbar (kein gültiges Land)."
            return render(request, "antraege/_ausweis_zeile_fertig.html",
                          {"text": text, "fehler": True})  # fmt: skip
    elif aktion == "verwerfen":
        a.ausweis_abweichung = False
        a.ausweis_erledigt = True
        a.save(update_fields=["ausweis_abweichung", "ausweis_erledigt"])
        text = "Nicht übernommen – Antrag bleibt wie angegeben."
    elif aktion == "amtsdokument":
        a.ausweis_abweichung = False
        a.ausweis_befund = "amtsdokument"
        a.ausweis_erledigt = True
        a.save(update_fields=["ausweis_abweichung", "ausweis_befund", "ausweis_erledigt"])
        text = "Als Bescheid (Amtsdokument) eingeordnet."
    else:
        raise Http404
    return render(request, "antraege/_ausweis_zeile_fertig.html", {"text": text, "fehler": False})


@rollen.recht_erforderlich("antraege.sehen")
def ausweis_miniatur(request, pk):
    """Kleine Vorschau des beim Scan gewählten Ausweis-Nachweises (Bild oder erste PDF-Seite),
    lokal gerendert, nicht serverseitig zwischengespeichert (der Nachweis liegt verschlüsselt)."""
    a = get_object_or_404(Antrag, pk=pk)
    d = a.ausweis_anhang
    if d is None:
        raise Http404
    inhalt = privatdateien.lesen(ANHANG_ORDNER, d.datei)
    if inhalt is None:
        raise Http404
    bild = _miniatur_bytes(inhalt, d.typ)
    if bild is None:
        raise Http404
    antwort = HttpResponse(bild, content_type="image/jpeg")
    antwort["Cache-Control"] = "private, max-age=600"  # nur im Browser des Mitarbeiters
    return antwort


def _miniatur_bytes(inhalt: bytes, typ: str):
    """Kleine JPEG-Vorschau aus einem Bild- oder PDF-Nachweis; None bei Fehler."""
    typ = (typ or "").lower()
    try:
        if "pdf" in typ:
            from apps.antraege import pdf_bilder

            return pdf_bilder.vorschau(inhalt)
        if "image" in typ:
            from PIL import Image, ImageOps

            bild = ImageOps.exif_transpose(Image.open(io.BytesIO(inhalt))).convert("RGB")
            bild.thumbnail((400, 400))
            puffer = io.BytesIO()
            bild.save(puffer, format="JPEG", quality=70)
            return puffer.getvalue()
    except Exception as fehler:  # noqa: BLE001 – nur eine Vorschau, nie kritisch
        log.warning("Ausweis-Miniatur fehlgeschlagen: %s", fehler)
    return None


@rollen.recht_erforderlich("antraege.bearbeiten")
def nachweise_importieren(request):
    """Nachweise im Stapel aus einem Altsystem übernehmen (ZIP + Liste nachweise.csv).

    „Nur prüfen" (Vorgabe) zeigt nur den Bericht; zum Übernehmen den Haken entfernen."""
    from apps.antraege import nachweis_import

    bericht = None
    if request.method == "POST":
        datei = request.FILES.get("zip")
        nur_pruefen = "nur_pruefen" in request.POST
        if not datei:
            messages.error(request, "Bitte eine ZIP-Datei auswählen.")
        else:
            try:
                if nur_pruefen:
                    bericht = nachweis_import.pruefen(datei)
                else:
                    bericht = nachweis_import.uebernehmen(datei)
                    messages.success(request, f"{bericht['zaehler']['ok']} Nachweise übernommen.")
            except nachweis_import.ImportFehler as fehler:
                messages.error(request, str(fehler))
    return render(request, "antraege/nachweise_importieren.html",
                  {"bericht": bericht, "status": nachweis_import.STATUS,
                   "max_mb": nachweis_import.MAX_MB})  # fmt: skip


@rollen.recht_erforderlich("antraege.bearbeiten")
def antraege_importieren(request):
    """Anträge im Stapel aus einem Altsystem übernehmen (antraege.csv – gleiche Spalten wie der
    Export). „Nur prüfen" (Vorgabe) zeigt nur den Bericht; zum Übernehmen den Haken entfernen."""
    from apps.antraege import antrag_import

    bericht, fehler_text = None, ""
    if request.method == "POST":
        datei = request.FILES.get("csv")
        uebernehmen = request.POST.get("aktion") == "uebernehmen"
        if not datei:
            fehler_text = "Bitte eine CSV-Datei auswählen."
        else:
            try:
                if uebernehmen:
                    bericht = antrag_import.uebernehmen(datei)
                    messages.success(request, f"{bericht['zaehler']['ok']} Anträge angelegt.")
                else:
                    bericht = antrag_import.pruefen(datei)
            except antrag_import.ImportFehler as fehler:
                fehler_text = str(fehler)
        # Probelauf per htmx: nur den Bericht zurückgeben, damit die gewählte Datei oben bleibt
        # (ein ganzer Seiten-Neuaufbau würde das Datei-Feld leeren).
        if request.headers.get("HX-Request") and not uebernehmen:
            return render(request, "antraege/_antraege_import_bericht.html",
                          {"bericht": bericht, "fehler_text": fehler_text})  # fmt: skip
        if fehler_text:
            messages.error(request, fehler_text)
    return render(request, "antraege/antraege_importieren.html",
                  {"bericht": bericht, "fehler_text": fehler_text})  # fmt: skip


@never_cache
@rollen.recht_erforderlich("antraege.sehen")
def auskunft_pdf(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    accessed.send(sender=Antrag, instance=a)
    return pdf_antwort(auskunft.antrag_pdf(a), f"auskunft-antrag-{a.nummer}.pdf")


EXPORT_SPALTEN = [
    "nummer", "eingegangen_am", "art", "status", "sprache", "kundennummer", "anrede", "vorname",
    "nachname", "geburtsdatum", "strasse", "plz", "ort", "telefon", "email", "familienstand",
    "staatsangehoerigkeit", "wochentage", "ausgabestelle", "personen", "nachricht",
]  # fmt: skip


def _wert(a, spalte):
    if spalte == "nummer":
        return a.nummer
    if spalte == "eingegangen_am":
        return f"{timezone.localtime(a.eingegangen_am):%Y-%m-%d %H:%M}"
    if spalte == "geburtsdatum":
        return f"{a.geburtsdatum:%Y-%m-%d}" if a.geburtsdatum else ""
    if spalte == "personen":
        return " | ".join(
            " ".join(
                t
                for t in (
                    p.vorname,
                    p.nachname,
                    f"{p.geburtsdatum:%Y-%m-%d}" if p.geburtsdatum else "",
                    f"({p.staatsangehoerigkeit})" if p.staatsangehoerigkeit else "",
                )
                if t
            )  # fmt: skip
            for p in a.personen.all()
        )
    return getattr(a, spalte)


@never_cache
@rollen.recht_erforderlich("antraege.sehen")
def export(request):
    """Die angezeigten Anträge als CSV, PDF oder per E-Mail (Eingangsreihenfolge)."""
    ansicht, _, antraege = _gefiltert(request)
    _, antraege = _sortiert(request, listenauswahl.filtern(request, antraege))
    puffer = io.StringIO()
    puffer.write("﻿")  # damit Tabellenprogramme die Umlaute richtig lesen
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(EXPORT_SPALTEN)
    for a in antraege.prefetch_related("personen"):
        schreiber.writerow([_wert(a, name) for name in EXPORT_SPALTEN])
    basis = f"antraege-{ansicht}-{timezone.localdate():%Y-%m-%d}"
    return listenexport.ausliefern(request, "Anträge", basis, puffer.getvalue(),
                                   weiter=reverse("antraege:liste"))  # fmt: skip


# --- Einstellungen (Admin) ---------------------------------------------------------------


@rollen.recht_erforderlich("einstellungen.antraege")
def einstellungen(request):
    form = EinstellungenForm(request.POST or None, instance=AntragEinstellungen.laden())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen der Anträge gespeichert.")
        return redirect("antraege:einstellungen")
    eigene = {t.sprache for t in AntragText.objects.exclude(einleitung="", bestaetigung="")}
    return render(
        request,
        "antraege/einstellungen.html",
        {
            "form": form,
            "sprachen": [(s, s.code in eigene) for s in sprachen.SPRACHEN],
        },
    )


@rollen.recht_erforderlich("einstellungen.antraege")
def texte(request, sprache):
    if sprache not in sprachen.NACH_CODE:
        raise Http404
    instanz = AntragText.objects.filter(sprache=sprache).first() or AntragText(sprache=sprache)
    form = TextForm(request.POST or None, instance=instanz)
    kontext = {"form": form, "s": sprachen.sprache(sprache), "t": sprachen.texte(sprache),
               "ki": sprache == "de" and uebersetzen_ki.verfuegbar()}  # fmt: skip
    if request.method == "POST" and form.is_valid():
        if "vorschau" in request.POST:
            kontext["vorschau"] = vorschau(request, form.save(commit=False))
        else:
            form.save()
            messages.success(request, "Texte gespeichert.")
            return redirect("antraege:einstellungen")
    return render(request, "antraege/texte.html", kontext)


def vorschau(request, eigene: AntragText) -> dict:
    """Die Texte so, wie Besucher sie sehen, mit erfundenen Beispielwerten."""
    from apps.antraege import views_oeffentlich as oe

    kontext = {**oe._kontext(eigene.sprache), "eigene": eigene}
    beispiel = SimpleNamespace(vorname="Erika", nachname="Beispiel", sprache=eigene.sprache,
                               staatsangehoerigkeit="")  # fmt: skip
    betreff, _, mail_html = oe.antwortmail(request, beispiel, eigene)
    return {
        "kopf": oe.eigener_bereich(eigene, "kopf", tafel=kontext["tafel_name"]),
        "fuss": oe.eigener_bereich(eigene, "fuss", tafel=kontext["tafel_name"]),
        "ueberschrift_zeigen": kontext["e"].ueberschrift_zeigen,
        "ueberschrift": oe._ueberschrift(kontext),
        "einleitung": html.anzeigen(
            eigene.einleitung, kontext["t"]["einleitung"], tafel=kontext["tafel_name"]
        ),  # fmt: skip
        "bestaetigung": oe._bestaetigung(kontext, ""),
        "mail_betreff": betreff,
        "mail_html": mail_html,
    }


# --- KI-Übersetzung der eigenen Texte (ADR 0082) ---------------------------------------------


@require_POST
@rollen.recht_erforderlich("einstellungen.antraege")
def uebersetzen(request):
    """Startet die Übersetzung; die Seite holt die Sprachen nacheinander (htmx), damit keine
    einzelne Anfrage zu lange dauert und man den Fortschritt sieht."""
    if not uebersetzen_ki.verfuegbar():
        messages.error(request, "Für die Übersetzung fehlt der API-Schlüssel (Anträge einstellen).")
        return redirect("antraege:texte", "de")
    if not uebersetzen_ki.deutsche_texte():
        messages.info(request, "Es gibt noch keine eigenen deutschen Texte zum Übersetzen.")
        return redirect("antraege:texte", "de")
    sprachliste = uebersetzen_ki.sprachen_ohne_deutsch()
    return render(request, "antraege/uebersetzen.html",
                  {"sprachliste": sprachliste, "erste": sprachliste[0]})  # fmt: skip


@require_POST
@rollen.recht_erforderlich("einstellungen.antraege")
def uebersetzen_sprache(request, sprache):
    """Eine Sprache übersetzen; die Antwort enthält die Zeile dazu und stößt die nächste an."""
    liste = uebersetzen_ki.sprachen_ohne_deutsch()
    codes = [s.code for s in liste]
    if sprache not in codes:
        raise Http404
    try:
        anzahl = uebersetzen_ki.sprache_uebersetzen(sprache)
        fehler = ""
    except uebersetzen_ki.UebersetzungsFehler as e:
        anzahl, fehler = 0, str(e)
    i = codes.index(sprache)
    return render(request, "antraege/_uebersetzen_schritt.html", {
        "s": liste[i], "anzahl": anzahl, "fehler": fehler,
        "naechste": liste[i + 1] if i + 1 < len(liste) else None,
    })  # fmt: skip
