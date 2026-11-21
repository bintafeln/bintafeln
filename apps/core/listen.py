"""Einheitliche Sortierung für Listen über ``?sort=…``.

Alle Übersichtslisten (Kunden, Adressen, Mitglieder, Spenden, Anträge) zeigen ihre Spaltenköpfe
gleich: anklickbar, mit Pfeil für die aktuelle Richtung (Tag ``{% sortkopf %}``). Diese Hilfen
setzen den gewählten ``?sort=…``-Wert in eine Reihenfolge um – entweder auf ein Queryset
(Datenbank) oder auf eine schon fertige Python-Liste (wenn Werte erst im Code entstehen).

Der Schlüssel steht wie beim CSV-Export in der URL; ein führendes „-“ bedeutet absteigend. Nur
bekannte Schlüssel sind erlaubt, sonst gilt die Vorgabe – so kann über die URL nichts
Unerwartetes sortiert werden."""

import re

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


# Spalten, die erst erscheinen, wenn die Person sie einschaltet (z. B. die Adressfelder in der
# Mitglieder- und der Spendenliste): je Liste mit ``standard_aus()`` angemeldet. Eingeschaltete
# stehen unter ``{liste}:an`` – so bleiben sie auch bei Konten aus, die ihre Wahl schon früher
# gespeichert haben.
_STANDARD_AUS: dict[str, set] = {}

# Die Adressfelder einer Person als wählbare Spalten (Schlüssel = Feld der Adresse). Listen, deren
# Zeilen an einer Adresse hängen, bieten sie alle an; die Titel sind zugleich die CSV-Überschriften.
ADRESS_SPALTEN = [("anrede", "Anrede"), ("strasse", "Straße"), ("plz", "PLZ"), ("ort", "Ort"),
                  ("telefon", "Telefon"), ("mobil", "Handy"), ("email", "E-Mail"),
                  ("email_weitere", "Weitere E-Mails"), ("geburtsdatum", "Geburtstag")]  # fmt: skip


def standard_aus(liste, schluessel) -> None:
    """Meldet Spalten einer Liste an, die in der Vorgabe ausgeblendet sind."""
    _STANDARD_AUS[liste] = set(schluessel)


def adress_spalten(benutzer) -> list[tuple[str, str]]:
    """Die Adressfelder als Spalten – nur für Konten, die das Adressbuch sehen dürfen."""
    from apps.konten import rollen

    return list(ADRESS_SPALTEN) if rollen.hat_recht(benutzer, "adressen.sehen") else []


def adress_werte(adresse) -> dict[str, str]:
    """Die Werte zu ``ADRESS_SPALTEN`` für den Export, je Überschrift."""
    werte = {titel: getattr(adresse, feld) or "" for feld, titel in ADRESS_SPALTEN}
    werte["Geburtstag"] = f"{adresse.geburtsdatum:%d.%m.%Y}" if adresse.geburtsdatum else ""
    return werte


def _ausgeblendet(benutzer, liste) -> set:
    daten = getattr(benutzer, "listen_spalten_aus", None) or {}
    standard = _STANDARD_AUS.get(liste, set()) - set(daten.get(f"{liste}:an", []))
    return set(daten.get(liste, [])) | standard


def sichtbare_spalten(benutzer, liste, schluessel, fest=()) -> set:
    """Welche Spaltenschlüssel sieht die Person? Feste sind immer dabei."""
    aus = _ausgeblendet(benutzer, liste)
    return {k for k in schluessel if k in fest or k not in aus}


def pdf_ohne(benutzer, liste, zuordnung: dict, fest=()) -> set:
    """Für den PDF-Export (``listenexport.ausliefern(ohne_spalten=…)``): die Überschriften der
    CSV-Spalten, die zu ausgeblendeten Listenspalten gehören. ``zuordnung``: je Spaltenschlüssel
    eine Überschrift oder mehrere."""
    weg = set()
    for schluessel in _ausgeblendet(benutzer, liste) - set(fest):
        namen = zuordnung.get(schluessel, ())
        weg |= {namen} if isinstance(namen, str) else set(namen)
    return weg


def spalten_wahl(benutzer, liste, spalten, fest=()) -> list[tuple]:
    """Für das Auswahlmenü: je Spalte (schluessel, titel, sichtbar, fest) – in der Reihenfolge,
    die die Person gewählt hat."""
    aus = _ausgeblendet(benutzer, liste)
    titel = dict(spalten)
    return [(k, titel[k], k not in aus or k in fest, k in fest)
            for k in reihenfolge(benutzer, liste, spalten)]  # fmt: skip


# --- Reihenfolge der Spalten je Person -------------------------------------------------------
# Unter „Spalten wählen“ lassen sich die Spalten verschieben. Gespeichert wird die Folge der
# Schlüssel unter ``{liste}:folge`` (neben den ausgeblendeten Spalten). Die Vorlagen geben ihre
# Zellen weiter in fester Reihenfolge aus und kennzeichnen sie mit ``{% spalte "schluessel" %}``;
# ``{% spaltenfolge folge %}…{% endspaltenfolge %}`` um die Tabelle ordnet sie um
# (``spalten_ordnen``). ``spalten`` einer Liste steht deshalb in der Reihenfolge der Vorlage.

_MARKE = re.compile(r"<!--s:([\w-]+)-->")
_ZEILE = re.compile(r"(<tr\b[^>]*>)(.*?)(</tr>)", re.S)


def _gemerkte_folge(benutzer, liste, spalten) -> list[str]:
    schluessel = [k for k, _ in spalten]
    daten = getattr(benutzer, "listen_spalten_aus", None) or {}
    return list(dict.fromkeys(k for k in daten.get(f"{liste}:folge", []) if k in schluessel))


def reihenfolge(benutzer, liste, spalten) -> list[str]:
    """Die Spaltenschlüssel in der Reihenfolge der Person; ohne eigene Wahl wie ``spalten``.
    Spalten, die sie noch nicht einsortiert hat (neu dazugekommen), stehen hinten."""
    vorn = _gemerkte_folge(benutzer, liste, spalten)
    return vorn + [k for k, _ in spalten if k not in vorn]


def eigene_folge(benutzer, liste, spalten) -> list[str] | None:
    """Wie ``reihenfolge``, aber ``None``, solange die Person nichts umgestellt hat – dann bleibt
    die Tabelle, wie die Vorlage sie ausgibt."""
    return (
        reihenfolge(benutzer, liste, spalten) if _gemerkte_folge(benutzer, liste, spalten) else None
    )


def spalten_ordnen(html: str, folge) -> str:
    """Ordnet in jeder Tabellenzeile die mit ``{% spalte %}`` gekennzeichneten Zellen nach
    ``folge``. Was vor der ersten Marke steht (Auswahlkästchen), bleibt vorn; Zellen, die in
    ``folge`` nicht vorkommen, bleiben in ihrer Reihenfolge am Ende. Die Marken fallen weg."""
    if "<!--s:" not in html:
        return html
    if not folge:
        return _MARKE.sub("", html)
    rang = {k: i for i, k in enumerate(folge)}

    def zeile(treffer):
        teile = _MARKE.split(treffer.group(2))
        if len(teile) == 1:
            return treffer.group(0)
        zellen = list(zip(teile[1::2], teile[2::2], strict=True))
        zellen.sort(key=lambda z: rang.get(z[0], len(rang)))  # stabil: Rest behält die Ordnung
        return treffer.group(1) + teile[0] + "".join(h for _, h in zellen) + treffer.group(3)

    return _ZEILE.sub(zeile, html)


def pdf_folge(benutzer, liste, zuordnung: dict, spalten) -> list[str]:
    """Für den PDF-Export (``listenexport.ausliefern(reihenfolge=…)``): die CSV-Überschriften in
    der Spaltenfolge der Person; leer, solange sie nichts umgestellt hat."""
    titel = []
    for schluessel in eigene_folge(benutzer, liste, spalten) or []:
        namen = zuordnung.get(schluessel, ())
        titel += [namen] if isinstance(namen, str) else list(namen)
    return titel


def spalten_aus_post(request, liste, spalten, fest=()) -> None:
    """Speichert die Angaben des Menüs „Spalten wählen“: sichtbare Spalten und – wenn die Seite
    sie mitschickt – deren Reihenfolge; „Reihenfolge zurücksetzen“ vergisst sie."""
    folge = request.POST.getlist("folge") if "folge" in request.POST else None
    if request.POST.get("folge_zuruecksetzen"):
        folge = []
    spalten_speichern(request.user, liste, request.POST.getlist("spalte"), spalten, fest, folge)


def spalten_speichern(benutzer, liste, gewaehlt, spalten, fest=(), folge=None) -> None:
    """Speichert die ausgeblendeten Spalten (alles außer ``gewaehlt`` und ``fest``) und – mit
    ``folge`` – die Reihenfolge; entspricht sie der Vorgabe (oder ist leer), wird sie vergessen."""
    gewaehlt = set(gewaehlt)
    aus = [k for k, _ in spalten if k not in fest and k not in gewaehlt]
    daten = dict(getattr(benutzer, "listen_spalten_aus", None) or {})
    daten[liste] = aus
    if folge is not None:
        schluessel = [k for k, _ in spalten]
        folge = list(dict.fromkeys(k for k in folge if k in schluessel))
        folge += [k for k in schluessel if k not in folge]
        if folge and folge != schluessel:
            daten[f"{liste}:folge"] = folge
        else:
            daten.pop(f"{liste}:folge", None)
    if liste in _STANDARD_AUS:
        daten[f"{liste}:an"] = sorted(_STANDARD_AUS[liste] & gewaehlt)
    benutzer.listen_spalten_aus = daten
    benutzer.save(update_fields=["listen_spalten_aus"])


# --- Zeilen je Seite, je Person gemerkt ------------------------------------------------------
# Alle Übersichtslisten zeigen in der Vorgabe 25 Zeilen je Seite. Wählt die Person eine andere
# Zahl, merkt bintafeln sie in ``Benutzer.liste_zeilen`` und wendet sie beim nächsten Aufruf –
# auch in anderen Listen und nach dem Abmelden – wieder an. Jede Liste gibt ihren GET-Parameter
# an (Anträge: „zeilen“, Kunden/Adressbuch: „anzahl“); gespeichert wird immer dasselbe Feld.
# Ein leerer Wert bedeutet „keine eigene Wahl“ – dann gilt die Vorgabe der jeweiligen Liste.

ZEILEN_WAHL = ("25", "50", "100", "alle")
# „alle“ zeigt höchstens so viele Zeilen auf einer Seite. Bei einem großen Bestand (z. B. über
# 10.000 Haushalte) bräuchten Server und Browser sonst viele Sekunden für eine einzige Seite –
# und weil die Wahl am Konto gemerkt wird, bei jedem Aufruf wieder. Darüber wird geblättert.
ALLE_HOECHSTENS = 500


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
    """Wandelt den Zeilen-Wert in eine Zahl für den Paginator um. ``"alle"`` → keine Teilung,
    solange die Liste höchstens :data:`ALLE_HOECHSTENS` Zeilen hat (sonst Seiten dieser Größe);
    leer oder unbekannt → ``standard`` (die Vorgabe der Liste)."""
    if wert == "alle":
        return min(max(gesamt, 1), ALLE_HOECHSTENS)
    return int(wert) if wert in ZEILEN_WAHL else standard


def filter_merken(request, liste: str, parameter, vorgaben: dict | None = None):
    """Merkt die Filter einer Liste am Konto, damit sie beim nächsten Aufruf wieder gelten.

    ``parameter``: die Filter der Liste (ohne Seite; Suchtext nur, wo er nach dem Öffnen eines
    Eintrags beim Zurückkommen noch gelten soll). Kommt die Seite ohne jede
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

    # Für den Knopf „Zurücksetzen“ ({% filter_zuruecksetzen %}): Er muss das Gemerkte vergessen
    request.filter_gemerkt = liste
    if request.GET.get("filter") == "zuruecksetzen":
        # Was der Knopf ausdrücklich behält (z. B. die Sortierung), bleibt auch gemerkt
        bleibt = QueryDict(mutable=True)
        for p in parameter:
            if p in request.GET:
                bleibt.setlist(p, request.GET.getlist(p))
        text = bleibt.urlencode()
        if alle.get(liste, "") != text:
            alle[liste] = text
            if not text:
                del alle[liste]
            speichern()
        return redirect(f"{request.path}?{text}" if text else request.path)
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
    if (alle.get(liste) and request.method == "GET" and not request.GET
            and not request.headers.get("HX-Request")):  # fmt: skip
        return redirect(f"{request.path}?{alle[liste]}")
    return None
