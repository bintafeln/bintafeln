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
