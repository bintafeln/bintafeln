"""Aufnahme-Assistent: einen Antrag Schritt für Schritt in den Kundenstamm übernehmen (ADR 0028).

Der Zwischenstand liegt in der Sitzung; gespeichert wird erst im letzten Schritt, in einer
Transaktion (aufnahme.uebernehmen).
"""

from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.antraege import aufnahme
from apps.antraege.models import Antrag
from apps.core.auswahl import mit_vorhandenem, staatsangehoerigkeiten
from apps.konten import rollen
from apps.kunden.models import Einkommensart, Haushalt, KundenEinstellungen, Kundengruppe

bearbeiter = rollen.recht_erforderlich("antraege.aufnehmen")

SCHRITTE = [
    ("kunde", "Kunde suchen"),
    ("abgleich", "Daten abgleichen"),
    ("personen", "Angehörige"),
    ("bescheid", "Bescheid und Gültigkeit"),
    ("gruppe", "Kundengruppe"),
    ("pruefen", "Prüfen und speichern"),
]
NAMEN = [s for s, _ in SCHRITTE]
EXTRA_PERSONEN = 3


def _schluessel(pk):
    return f"aufnahme_{pk}"


def _zustand(request, pk) -> dict:
    return request.session.setdefault(_schluessel(pk), {})


def _speichern(request, pk, zustand):
    request.session[_schluessel(pk)] = zustand
    request.session.modified = True


def _weiter(antrag, schritt):
    return redirect("antraege:aufnahme_schritt", pk=antrag.pk,
                    schritt=NAMEN[NAMEN.index(schritt) + 1])  # fmt: skip


def _antrag_wert(antrag, feld) -> str:
    wert = getattr(antrag, feld)
    return wert.isoformat() if feld == "geburtsdatum" and wert else (wert or "")


def _bestand(h: Haushalt | None) -> dict:
    """Werte des bestehenden Haushalts und seiner Hauptperson (als Text)."""
    if h is None:
        return {}
    hp = h.hauptperson
    werte = {}
    for feld, _, zum_haushalt in aufnahme.FELDER:
        quelle = h if zum_haushalt else hp
        wert = getattr(quelle, feld, "") if quelle else ""
        werte[feld] = wert.isoformat() if feld == "geburtsdatum" and wert else (wert or "")
    return werte


@bearbeiter
def start(request, pk):
    """Beginnt die Aufnahme neu (verwirft einen angefangenen Zwischenstand)."""
    a = get_object_or_404(Antrag, pk=pk, papierkorb_am__isnull=True)
    _speichern(request, a.pk, {})
    return redirect("antraege:aufnahme_schritt", pk=a.pk, schritt="kunde")


@bearbeiter
def schritt(request, pk, schritt):
    if schritt not in NAMEN:
        raise Http404
    a = get_object_or_404(Antrag, pk=pk, papierkorb_am__isnull=True)
    z = _zustand(request, a.pk)
    if schritt != "kunde" and "haushalt" not in z:
        return redirect("antraege:aufnahme_schritt", pk=a.pk, schritt="kunde")
    h = Haushalt.objects.filter(kundennummer=z.get("haushalt")).first() if z.get(
        "haushalt") else None  # fmt: skip
    kontext = {"a": a, "schritt": schritt, "schritte": SCHRITTE, "h": h, "z": z,
               "nr": NAMEN.index(schritt) + 1}  # fmt: skip
    fehler = None
    if request.method == "POST":
        fehler = globals()[f"_post_{schritt}"](request, a, z, h)
        if fehler is None:
            _speichern(request, a.pk, z)
            if schritt == "pruefen":
                return redirect("antraege:aufnahme_fertig", pk=a.pk)
            return _weiter(a, schritt)
    kontext["fehler"] = fehler
    kontext.update(globals()[f"_kontext_{schritt}"](request, a, z, h))
    return render(request, "antraege/aufnahme.html", kontext)


# --- 1. Kunde suchen ------------------------------------------------------------------------


def _kontext_kunde(request, a, z, h):
    return {"treffer": aufnahme.treffer(a)}


def _post_kunde(request, a, z, h):
    wahl = request.POST.get("haushalt", "")
    if wahl == "neu":
        z.update({"haushalt": None, "werte": {}, "personen": None})
        return None
    if not Haushalt.objects.filter(kundennummer=wahl).exists():
        return "Bitte einen Kunden aus der Liste oder „Neuer Kunde“ wählen."
    z.update({"haushalt": wahl, "werte": {}, "personen": None})
    return None


# --- 2. Daten abgleichen --------------------------------------------------------------------


def _kontext_abgleich(request, a, z, h):
    bestand = _bestand(h)
    gewaehlt = z.get("werte") or {}
    zeilen = []
    for feld, titel, _ in aufnahme.FELDER:
        alt, neu = bestand.get(feld, ""), _antrag_wert(a, feld)
        if feld in gewaehlt:
            wahl = "antrag" if gewaehlt[feld] == neu and neu != alt else "bestand"
        else:
            wahl = "antrag" if neu and (not alt or h is None) else "bestand"
        zeilen.append({"feld": feld, "titel": titel, "bestand": alt, "antrag": neu,
                       "gleich": alt == neu, "wahl": wahl})  # fmt: skip
    return {"zeilen": zeilen, "neu": h is None}


def _post_abgleich(request, a, z, h):
    bestand = _bestand(h)
    werte = {}
    for feld, _, _ in aufnahme.FELDER:
        if h is None or request.POST.get(f"wahl_{feld}") == "antrag":
            werte[feld] = _antrag_wert(a, feld)
        else:
            werte[feld] = bestand.get(feld, "")
    if not werte.get("vorname") or not werte.get("nachname"):
        return "Vor- und Nachname sind nötig."
    z["werte"] = werte
    return None


# --- 3. Angehörige --------------------------------------------------------------------------


def _als_dict(p, pk=None) -> dict:
    datum = p.geburtsdatum.isoformat() if p.geburtsdatum else ""
    return {"pk": pk, "vorname": p.vorname, "nachname": p.nachname, "geburtsdatum": datum,
            "staatsangehoerigkeit": p.staatsangehoerigkeit}  # fmt: skip


def _vorschlag_personen(a, h) -> list[dict]:
    """Angehörige des Haushalts, dazu die aus dem Antrag, die dort noch fehlen."""
    personen = [_als_dict(p, p.pk) for p in h.personen.filter(ist_hauptperson=False)] if h else []
    for p in a.personen.all():
        schon_da = any(
            aufnahme.namens_aehnlichkeit(p.vorname, p.nachname, x["vorname"], x["nachname"]) > 0.85
            for x in personen
        )
        if not schon_da:
            personen.append(_als_dict(p))
    return personen


def _kontext_personen(request, a, z, h):
    personen = z.get("personen")
    if personen is None:
        personen = _vorschlag_personen(a, h)
    leer = {
        "pk": None,
        "vorname": "",
        "nachname": "",
        "geburtsdatum": "",
        "staatsangehoerigkeit": "",
    }
    staaten = staatsangehoerigkeiten()
    for p in personen:  # gespeicherte Werte, die nicht in der Liste stehen, bleiben wählbar
        staaten = mit_vorhandenem(staaten, p.get("staatsangehoerigkeit", ""))
    return {
        "personen": personen + [dict(leer) for _ in range(EXTRA_PERSONEN)],
        "staaten": staaten if KundenEinstellungen.laden().staatsangehoerigkeit_erfassen else None,
    }


def _post_personen(request, a, z, h):
    personen = []
    for i in range(int(request.POST.get("anzahl", "0") or 0)):
        if request.POST.get(f"p{i}_weg"):
            continue
        vorname = request.POST.get(f"p{i}_vorname", "").strip()[:100]
        if not vorname:
            continue
        datum = request.POST.get(f"p{i}_geburtsdatum", "")
        try:
            datum = timezone.datetime.fromisoformat(datum).date().isoformat() if datum else ""
        except ValueError:
            return f"Geburtsdatum von {vorname} ist kein gültiges Datum."
        pk = request.POST.get(f"p{i}_pk", "")
        personen.append({"pk": int(pk) if pk.isdigit() else None, "vorname": vorname,
                         "nachname": request.POST.get(f"p{i}_nachname", "").strip()[:100],
                         "geburtsdatum": datum})  # fmt: skip
        if f"p{i}_staatsangehoerigkeit" in request.POST:  # nur, wenn sie erfasst wird
            personen[-1]["staatsangehoerigkeit"] = request.POST[
                f"p{i}_staatsangehoerigkeit"
            ].strip()[:100]
    z["personen"] = personen
    return None


# --- 4. Bescheid und Gültigkeit -------------------------------------------------------------


def _kontext_bescheid(request, a, z, h):
    e = KundenEinstellungen.laden()
    arten = Einkommensart.objects.filter(aktiv=True).order_by("bezeichnung")
    aktuell = z.get("einkommensart") or (h.einkommensart_id if h else None)
    if aktuell and not arten.filter(pk=aktuell).exists():
        # gespeicherter Wert bleibt wählbar (CLAUDE.md)
        arten = Einkommensart.objects.filter(Q(aktiv=True) | Q(pk=aktuell)).order_by("bezeichnung")
    gueltigkeiten = aufnahme.gueltigkeit_auswahl(timezone.localdate(), e)
    gewaehlt = z.get("gueltig_bis", "")
    return {
        "arten": arten,
        "art_gewaehlt": aktuell,
        "gueltigkeiten": gueltigkeiten,
        "gueltig_gewaehlt": gewaehlt,
        "gueltig_eigen": bool(gewaehlt) and gewaehlt not in dict(gueltigkeiten),
        "bisher_gueltig": h.ausweis_gueltig_bis if h else None,
    }


def _post_bescheid(request, a, z, h):
    art = request.POST.get("einkommensart", "")
    gueltig = request.POST.get("gueltig_bis", "")
    eigenes = request.POST.get("gueltig_eigenes", "")
    if gueltig == "eigenes":
        gueltig = eigenes
    if art and not Einkommensart.objects.filter(pk=art).exists():
        return "Bitte eine Bescheidart aus der Liste wählen."
    if art and not gueltig:
        return "Bitte festlegen, bis wann der Ausweis gilt."
    if gueltig:
        try:
            datum = timezone.datetime.fromisoformat(gueltig).date()
        except ValueError:
            return "Das Datum der Gültigkeit ist ungültig."
        if datum < timezone.localdate():
            return "Die Gültigkeit darf nicht in der Vergangenheit liegen."
        gueltig = datum.isoformat()
    z["einkommensart"] = int(art) if art else None
    z["gueltig_bis"] = gueltig if art else ""
    return None


# --- 5. Kundengruppe ------------------------------------------------------------------------


def _kontext_gruppe(request, a, z, h):
    gruppen = aufnahme.freie_gruppen(h)
    gewaehlt = z.get("kundengruppe") or (h.kundengruppe_id if h else None)
    return {"gruppen": gruppen, "gruppe_gewaehlt": gewaehlt,
            "wunsch": a.ausgabestelle, "wunsch_tage": a.wochentage}  # fmt: skip


def _post_gruppe(request, a, z, h):
    wahl = request.POST.get("kundengruppe", "")
    if not wahl:
        z["kundengruppe"] = None
        return None
    frei = {str(g["gruppe"].pk) for g in aufnahme.freie_gruppen(h)}
    if wahl not in frei:
        return "Diese Kundengruppe ist voll oder nicht aktiv. Bitte eine andere wählen."
    z["kundengruppe"] = int(wahl)
    return None


# --- 6. Prüfen und speichern ----------------------------------------------------------------


def _kontext_pruefen(request, a, z, h):
    werte = z.get("werte") or {}
    personen = z.get("personen")
    if personen is None:
        personen = _vorschlag_personen(a, h)
    return {
        "felder": [(t, werte.get(f, "")) for f, t, _ in aufnahme.FELDER],
        "personen_liste": personen,
        "art": Einkommensart.objects.filter(pk=z.get("einkommensart")).first(),
        "gruppe": Kundengruppe.objects.filter(pk=z.get("kundengruppe")).first(),
        "naechste_nummer": aufnahme.naechste_kundennummer() if h is None else h.kundennummer,
    }


def _post_pruefen(request, a, z, h):
    if not z.get("werte"):
        return "Bitte zuerst die Daten abgleichen."
    if z.get("personen") is None:
        z["personen"] = _vorschlag_personen(a, h)
    if z.get("haushalt") and h is None:
        return "Der gewählte Kunde existiert nicht mehr. Bitte neu beginnen."
    neu = aufnahme.uebernehmen(a, z, request.user.get_username())
    z["ergebnis"] = neu.kundennummer
    messages.success(
        request,
        f"Antrag {a.nummer} aufgenommen: Kunde {neu.kundennummer}"
        f"{' (neu angelegt)' if h is None else ' (aktualisiert)'}.",
    )
    return None


@bearbeiter
def fertig(request, pk):
    a = get_object_or_404(Antrag, pk=pk)
    z = request.session.get(_schluessel(a.pk), {})
    nummer = z.get("ergebnis") or a.kundennummer
    h = get_object_or_404(Haushalt, kundennummer=nummer)
    return render(request, "antraege/aufnahme_fertig.html", {"a": a, "h": h})
