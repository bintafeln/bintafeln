"""Welche Kunden ein Konto aufrufen darf (Zuordnung zu Ausgabestellen, ADR 0034).

Wer einer oder mehreren Ausgabestellen zugeordnet ist, ruft nur Haushalte auf, deren
Kundengruppe zu einer dieser Ausgabestellen gehört – außer mit dem Recht
„kunden.alle_ausgabestellen“ (Admin immer). Ohne Zuordnung gibt es keine Einschränkung.
"""

from django.core.exceptions import PermissionDenied

from apps.konten import rollen


def stellen(benutzer) -> list | None:
    """Ausgabestellen, auf die das Konto beschränkt ist; None = keine Einschränkung."""
    if not getattr(benutzer, "is_authenticated", False):
        return []
    if rollen.hat_recht(benutzer, "kunden.alle_ausgabestellen"):
        return None
    gemerkt = getattr(benutzer, "_bintafeln_stellen", False)
    if gemerkt is not False:
        return gemerkt
    eigene = list(benutzer.ausgabestellen.order_by("name"))
    benutzer._bintafeln_stellen = eigene or None
    return benutzer._bintafeln_stellen


def _namen(liste) -> str:
    namen = [f"„{s.name}“" for s in liste]
    return namen[0] if len(namen) == 1 else ", ".join(namen[:-1]) + " und " + namen[-1]


def sperrgrund(benutzer, haushalt) -> str:
    """Leer, wenn erlaubt; sonst ein Satz, warum dieser Kunde nicht aufgerufen werden darf."""
    eigene = stellen(benutzer)
    if eigene is None:
        return ""
    gruppe = haushalt.kundengruppe
    stelle = gruppe.ausgabestelle if gruppe else None
    if stelle is not None and stelle.pk in {s.pk for s in eigene}:
        return ""
    zugeordnet = f"Sie sind der Ausgabestelle {_namen(eigene)} zugeordnet" if len(eigene) == 1 \
        else f"Sie sind den Ausgabestellen {_namen(eigene)} zugeordnet"  # fmt: skip
    if stelle is None:
        wo = (f"gehört zur Kundengruppe „{gruppe.name}“ ohne Ausgabestelle" if gruppe
              else "ist keiner Kundengruppe zugeordnet")  # fmt: skip
    else:
        wo = f"gehört zur Ausgabestelle „{stelle.name}“"
        if gruppe:
            wo += f" (Kundengruppe „{gruppe.name}“)"
    return (f"Kunde {haushalt.kundennummer} {wo}. {zugeordnet} und dürfen nur deren Kunden "
            "aufrufen. Wenn der Kunde trotzdem hier bedient werden soll, wenden Sie sich bitte an "
            "das Büro oder einen Admin.")  # fmt: skip


def pruefen(benutzer, haushalt) -> None:
    """Wirft PermissionDenied mit der Begründung (erscheint auf der Seite „Kein Zugriff“)."""
    grund = sperrgrund(benutzer, haushalt)
    if grund:
        raise PermissionDenied(grund)


def filtern(haushalte, benutzer):
    """Schränkt eine Haushalt-Abfrage auf die eigenen Ausgabestellen ein."""
    eigene = stellen(benutzer)
    if eigene is None:
        return haushalte
    return haushalte.filter(kundengruppe__ausgabestelle__in=eigene)


def haushalt(benutzer, kundennummer, abfrage=None):
    """Haushalt laden (404, wenn es ihn nicht gibt) und den Zugang prüfen (403 mit Grund)."""
    from django.shortcuts import get_object_or_404

    from apps.kunden.models import Haushalt

    abfrage = abfrage if abfrage is not None else Haushalt.objects
    h = get_object_or_404(
        abfrage.select_related("kundengruppe__ausgabestelle"), kundennummer=kundennummer
    )
    pruefen(benutzer, h)
    return h


def pruefen_nummer(benutzer, kundennummer) -> None:
    """Für Daten an einer Kundennummer (Notizen, Dokumente), auch wenn der Haushalt fehlt."""
    from apps.kunden.models import Haushalt

    if stellen(benutzer) is None:
        return
    h = (
        Haushalt.objects.select_related("kundengruppe__ausgabestelle")
        .filter(kundennummer=kundennummer)
        .first()
    )
    if h is None:
        raise PermissionDenied(
            f"Kunde {kundennummer} steht nicht mehr im Kundenstamm. Daten dazu sieht nur, wer "
            "Kunden aller Ausgabestellen aufrufen darf."
        )
    pruefen(benutzer, h)
