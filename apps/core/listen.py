"""Einheitliche Sortierung für Listen über ``?sort=…``.

Alle Übersichtslisten (Kunden, Adressen, Mitglieder, Spenden, Anträge) zeigen ihre Spaltenköpfe
gleich: anklickbar, mit Pfeil für die aktuelle Richtung (Tag ``{% sortkopf %}``). Diese Hilfen
setzen den gewählten ``?sort=…``-Wert in eine Reihenfolge um – entweder auf ein Queryset
(Datenbank) oder auf eine schon fertige Python-Liste (wenn Werte erst im Code entstehen).

Der Schlüssel steht wie beim CSV-Export in der URL; ein führendes „-“ bedeutet absteigend. Nur
bekannte Schlüssel sind erlaubt, sonst gilt die Vorgabe – so kann über die URL nichts
Unerwartetes sortiert werden."""

from django.db.models import F


def sortieren(queryset, sort, felder, standard):
    """Sortiert ``queryset`` nach dem GET-Wert ``sort``.

    ``felder``: Schlüssel → Tupel der ``order_by``-Felder (Name als Text oder fertiger Ausdruck).
    Unbekannter Schlüssel → ``standard``. Leere Werte stehen immer am Ende. Gibt das sortierte
    Queryset und den tatsächlich verwendeten Sortierwert zurück (für den Pfeil im Spaltenkopf)."""
    sort = sort if (sort or "").lstrip("-") in felder else standard
    ab = sort.startswith("-")
    ausdruecke = []
    for f in felder[sort.lstrip("-")]:
        a = F(f) if isinstance(f, str) else f
        ausdruecke.append(a.desc(nulls_last=True) if ab else a.asc(nulls_last=True))
    return queryset.order_by(*ausdruecke), sort


def sortieren_liste(zeilen, sort, schluessel, standard):
    """Wie :func:`sortieren`, aber für eine schon geladene Python-Liste (z. B. mit im Code
    gerechneten Spalten). ``schluessel``: Spalte → Funktion, die den Sortierwert einer Zeile
    liefert. Gibt die sortierte Liste und den verwendeten Sortierwert zurück."""
    sort = sort if (sort or "").lstrip("-") in schluessel else standard
    zeilen = sorted(zeilen, key=schluessel[sort.lstrip("-")], reverse=sort.startswith("-"))
    return zeilen, sort


# --- Spaltenauswahl je Person ----------------------------------------------------------------
# Jede Person blendet in einer Liste selbst Spalten aus. Gespeichert wird je Liste die Menge der
# ausgeblendeten Schlüssel in ``Benutzer.listen_spalten_aus`` ({liste: [schluessel]}). Feste
# Spalten (z. B. die, die den Datensatz öffnet) lassen sich nie ausblenden. Kundenliste und
# Antragsliste haben eigene ältere Felder und nutzen diese Helfer nicht.


def _ausgeblendet(benutzer, liste) -> set:
    return set((getattr(benutzer, "listen_spalten_aus", None) or {}).get(liste, []))


def sichtbare_spalten(benutzer, liste, schluessel, fest=()) -> set:
    """Welche Spaltenschlüssel sieht die Person? Feste sind immer dabei."""
    aus = _ausgeblendet(benutzer, liste)
    return {k for k in schluessel if k in fest or k not in aus}


def spalten_wahl(benutzer, liste, spalten, fest=()) -> list[tuple]:
    """Für das Auswahlmenü: je Spalte (schluessel, titel, sichtbar, fest)."""
    aus = _ausgeblendet(benutzer, liste)
    return [(k, t, k not in aus or k in fest, k in fest) for k, t in spalten]


def spalten_speichern(benutzer, liste, gewaehlt, spalten, fest=()) -> None:
    """Speichert die ausgeblendeten Spalten (alles außer ``gewaehlt`` und ``fest``)."""
    gewaehlt = set(gewaehlt)
    aus = [k for k, _ in spalten if k not in fest and k not in gewaehlt]
    daten = dict(getattr(benutzer, "listen_spalten_aus", None) or {})
    daten[liste] = aus
    benutzer.listen_spalten_aus = daten
    benutzer.save(update_fields=["listen_spalten_aus"])


# --- Zeilen je Seite, je Person gemerkt ------------------------------------------------------
# Alle Übersichtslisten zeigen in der Vorgabe 25 Zeilen je Seite. Wählt die Person eine andere
# Zahl, merkt bintafeln sie in ``Benutzer.liste_zeilen`` und wendet sie beim nächsten Aufruf –
# auch in anderen Listen und nach dem Abmelden – wieder an. Jede Liste gibt ihren GET-Parameter
# an (Anträge: „zeilen“, Kunden/Adressbuch: „anzahl“); gespeichert wird immer dasselbe Feld.
# Ein leerer Wert bedeutet „keine eigene Wahl“ – dann gilt die Vorgabe der jeweiligen Liste.

ZEILEN_WAHL = ("25", "50", "100", "alle")


def zeilenzahl(request, param: str = "zeilen") -> str:
    """Gewählte Zeilen je Seite: aus ``?<param>=`` lesen und je Person merken, sonst die zuletzt
    gemerkte verwenden. Gibt einen Wert aus :data:`ZEILEN_WAHL` oder ``""`` (keine eigene Wahl –
    die Liste nimmt dann ihre Vorgabe) zurück."""
    benutzer = getattr(request, "user", None)
    wert = request.GET.get(param)
    if wert in ZEILEN_WAHL:
        if getattr(benutzer, "liste_zeilen", None) != wert and getattr(benutzer, "pk", None):
            benutzer.liste_zeilen = wert
            benutzer.save(update_fields=["liste_zeilen"])
        return wert
    return getattr(benutzer, "liste_zeilen", "") or ""


def je_seite(wert: str, gesamt: int, standard: int = 25) -> int:
    """Wandelt den Zeilen-Wert in eine Zahl für den Paginator um. ``"alle"`` → keine Teilung;
    leer oder unbekannt → ``standard`` (die Vorgabe der Liste)."""
    if wert == "alle":
        return max(gesamt, 1)
    return int(wert) if wert in ZEILEN_WAHL else standard


def filter_merken(request, liste: str, parameter, vorgaben: dict | None = None):
    """Merkt die Filter einer Liste am Konto, damit sie beim nächsten Aufruf wieder gelten.

    ``parameter``: die Filter der Liste (ohne Suchtext und Seite). Kommt die Seite ohne jede
    Angabe, leitet die Funktion auf die gemerkten Filter um (Rückgabe: die Umleitung, sonst
    ``None``). ``?filter=zuruecksetzen`` vergisst sie. ``vorgaben``: Werte, die nicht gemerkt
    werden, solange sie der Vorgabe entsprechen – z. B. der heutige Ausgabetag, der sonst am
    nächsten Tag noch der gestrige wäre."""
    from django.http import QueryDict
    from django.shortcuts import redirect

    benutzer = request.user
    alle = dict(benutzer.listen_filter or {})

    def speichern():
        benutzer.listen_filter = alle
        benutzer.save(update_fields=["listen_filter"])

    if request.GET.get("filter") == "zuruecksetzen":
        if alle.pop(liste, None) is not None:
            speichern()
        return redirect(request.path)
    if any(p in request.GET for p in parameter):
        gemerkt = QueryDict(mutable=True)
        for p in parameter:
            werte = request.GET.getlist(p)
            if p in request.GET and werte != [(vorgaben or {}).get(p, object())]:
                gemerkt.setlist(p, werte)
        text = gemerkt.urlencode()
        if alle.get(liste, "") != text:
            alle[liste] = text
            speichern()
        return None
    if alle.get(liste) and not request.GET and not request.headers.get("HX-Request"):
        return redirect(f"{request.path}?{alle[liste]}")
    return None
